import base64
import markdown
import logging
import uuid
import requests as http_requests
from itertools import chain
#django imports
from django.shortcuts import render, get_object_or_404, redirect
from django.views import generic
from django.db.models import Q, QuerySet
from django.http import HttpResponse
from django.http import FileResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
# rest imports 
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
# django objects 
from .forms import TextEntryForm, ChangeProfileForm
from .models import Like, TextEntry, Author, Follow, Comment, Node
# serializers
from .serializers import (
    EntrySerializer, AuthorSerializer, LikeSerializer, 
    CommentSerializer, FollowSerializer,
)
# Utility functions 
from .utils import (
    NOT_DELETED, convert_remote_author_to_local, get_author_by_serial, get_current_author,
    author_exists, get_source_entry_url, validate_create_author, friends,
    fetch_remote_author, can_view_entry, render_markdown_entries,
    get_page_args, paginate_set, build_paginated_response,
    fetch_github_entries, remote_node_get, authenticate_remote_node, 
    send_entry_to_followers, send_follow_to_inbox, send_comment_to_inbox, 
    send_like_to_inbox, send_comment_to_inbox, send_like_to_followers, send_comment_to_followers,
    convert_remote_entry_to_local, remote_node_get_authors, remote_node_get_entries,
    get_or_create_remote_author_from_fqid, upsert_remote_author,
)

logger = logging.getLogger(__name__)

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


# Web-UI Views 
def index(request):
    if not request.user.is_authenticated: # authenticated personal page view
        return redirect('/social_distribution/login')
    
    nodes = Node.objects.all()

    author = get_current_author(request)

    # Fetch new GitHub entries for the logged-in author (no cooldown) and push
    # them to remote followers, since this is the authoritative node for this author.
    new_github_entries = fetch_github_entries(author, 0)
    for github_entry in new_github_entries:
        send_entry_to_followers(github_entry, request)

    # 1. Own entries (all visibilities)
    own_entries = list(
        TextEntry.objects.filter(author=author).filter(NOT_DELETED)
    )

    # 2. Entries from authors you follow
    followed_entries = []
    people_you_follow = Follow.objects.filter(follower=author, approved=True)

    for follow in people_you_follow:
        following_author = follow.following

        # Fetch GitHub entries for followed authors to keep the local DB current.
        # Do not push these — the remote author's own node is responsible for that.
        fetch_github_entries(following_author, 1)

        visibility_filter = Q(visibility="PUBLIC") | Q(visibility="UNLISTED")
        if friends(author, following_author):
            visibility_filter |= Q(visibility="FRIENDS")

        entries_from_author = list(
            TextEntry.objects.filter(
                author=following_author
            ).filter(NOT_DELETED).filter(visibility_filter)
        )
        followed_entries.extend(entries_from_author)

    # 3. All public entries on this node (includes authors not followed)
    all_local_public = list(
        TextEntry.objects.filter(visibility="PUBLIC").filter(NOT_DELETED)
    )

    # 4. Remote public entries from connected nodes
    remote_public_entries = []
    for node in nodes:
        remote_authors = remote_node_get_authors(node, auth_required=False)
        for remote_author in remote_authors:
            r_entries = remote_node_get_entries(node, remote_author, auth_required=False)
            remote_public_entries.extend(r_entries)

    # Merge all four sources into one deduplicated, sorted stream.
    # Key: remote_fqid for remote entries, "local:{pk}" for local entries.
    seen = set()
    stream = []
    for entry in chain(own_entries, followed_entries, all_local_public, remote_public_entries):
        key = entry.remote_fqid if entry.remote_fqid else f"local:{entry.pk}"
        if key in seen:
            continue
        seen.add(key)
        entry.url = get_source_entry_url(entry)
        entry.image_url = build_entry_image_url(entry)
        stream.append(entry)

    stream.sort(key=lambda e: e.published, reverse=True)
    render_markdown_entries(stream)

    return render(request, "social_distribution/index.html", {
        'stream': stream,
        'author': author.name,
        'picture_url': author.picture,
        'public_url': author.username,
    })


def profile_view(request, username):
    author = get_object_or_404(Author, username=username)

    current_author = None
    if request.user.is_authenticated:
        current_author = get_current_author(request)

    is_own_profile = current_author == author if current_author else False

    # Fetch new GitHub entries for this author (no cooldown on profile visit).
    # Only push to followers if the logged-in user is the profile owner
    new_github_entries = fetch_github_entries(author, 0)
    if is_own_profile:
        for github_entry in new_github_entries:
            send_entry_to_followers(github_entry, request)

    entry_filter = Q(visibility='PUBLIC')
    if is_own_profile:
        # owner sees all their own entries
        entry_filter |= Q(visibility='FRIENDS') | Q(visibility='UNLISTED')
    elif current_author:
        if friends(current_author, author):
            entry_filter |= Q(visibility='FRIENDS')
    
    entries = TextEntry.objects.filter(author=author).filter(NOT_DELETED).filter(entry_filter).order_by("-published")

    for entry in entries:
        entry.image_url = build_entry_image_url(entry)

    render_markdown_entries(entries)

    is_following = False
    is_follow_requested = False
    if current_author and not is_own_profile:
        is_following = Follow.objects.filter(
            follower = current_author,
            following=author,
            approved=True
        ).exists()
        if not is_following:
            is_follow_requested = Follow.objects.filter(
                follower=current_author,
                following=author,
                approved=False
            ).exists()


    return render(request, "social_distribution/publicprofile.html", {
        'latest_entry_list' : entries,
        'author' : author.name,
        'author_username': author.username,
        'picture_url' : author.picture,
        'is_following': is_following,
        'is_follow_requested': is_follow_requested,
        'is_own_profile': is_own_profile
    })

class DetailView(generic.DetailView):
    model = TextEntry
    context_object_name = "entry"
    template_name = "social_distribution/detail.html"

    def get_object(self, queryset=None):
        entry = super().get_object(queryset)
        # Deleted entries are never accessible — return a hard 404
        # rather than rendering the page with is_visible=False.
        if entry.is_deleted:
            from django.http import Http404
            raise Http404("Entry not found.")
        return entry

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entry = context['entry']
        user = self.request.user
        entry.image_url = build_entry_image_url(entry)

        # Determine visibility and set is_visible in context.
        if entry.visibility in ("PUBLIC", "UNLISTED"):
            is_visible = True
        elif entry.visibility == "FRIENDS":
            if not user.is_authenticated:
                is_visible = False
            else:
                viewer = get_author_by_serial(user.username)
                is_visible = (viewer == entry.author) or friends(viewer, entry.author)
        else:
            is_visible = False

        context['is_visible'] = is_visible

        # If the entry isn't visible, don't fetch likes, comments, or rendering markdown
        if not is_visible:
            context['likes_count'] = 0
            context['has_liked'] = False
            context['comments'] = []
            return context

        # Markdown rendering
        if entry.content_type == 'text/markdown':
            entry.content_rendered = markdown.markdown(entry.content)
            entry.header_rendered = markdown.markdown(entry.title)

        context['likes_count'] = Like.objects.filter(object_url=entry.fqid).count()
        
        # Check if user has liked this entry
        if user.is_authenticated:
            context['has_liked'] = Like.objects.filter(
                author__username=user.username, object_url=entry.fqid
            ).exists()
        else:
            context['has_liked'] = False
        
        # Get all comments for this entry
        comments = Comment.objects.filter(local_entry=entry).order_by('-published')
        # annotate like counts and whether current user liked each comment
        comment_list = []
        for comment in comments:
            comment.likes_count = Like.objects.filter(object_url=comment.fqid).count()
            if user.is_authenticated:
                comment.user_liked = Like.objects.filter(
                    author__username=user.username, object_url=comment.fqid
                ).exists()
            else:
                comment.user_liked = False
            comment_list.append(comment)
        context['comments'] = comment_list

        return context 


@login_required
def discover_remote_authors(request):
    current_author = get_current_author(request)
    remote_authors = []

    for node in Node.objects.filter(is_enabled=True):
        try:
            response = remote_node_get(node, "api/authors/", auth_required=True)
            if response is None or response.status_code != 200:
                continue
            data = response.json()
            for author_data in data.get('authors', []):
                author = upsert_remote_author(author_data)
                if author:
                    remote_authors.append(author)
        except Exception as e:
            logger.error(f"Failed to fetch authors from {node.url}: {e}")

    # follow status
    following_ids = set(
        Follow.objects.filter(follower=current_author).values_list('following_id', flat=True)
    )
    for author in remote_authors:
        author.is_followed = author.id in following_ids

    return render(request, "social_distribution/discover.html", {
        "remote_authors": remote_authors
    })

def login_view(request):
    if request.user.is_authenticated:
        # if authenticated, redirect to index
        return redirect("/social_distribution")
    # if not logged in, render the login page
    return render(request, "login.html")


@login_required(login_url='/social_distribution/login')
def newentry_view(request):
    form = TextEntryForm()
    return render(request, "social_distribution/newentry.html", {'form': form})


@login_required(login_url='/social_distribution/login')
def changeprofile_view(request):
    author = get_current_author(request)
    return render(request, "changeprofile.html", {
        'name' : author.name, 'description' : author.description, 
        'picture' : author.picture, 'github' : author.github 
    })

def nodes_view(request):
    dataToSend = { "nodetuples": [] }
    nodes = Node.objects.all()

    for node in nodes:
        try:
            response = remote_node_get(node, "api/authors/", auth_required=True)
            if response is None:
                status = "Node is disabled or unreachable"
            elif response.status_code == 200:
                author_count = response.json().get("count", "N/A")
                status = str(response.status_code) + " | " + str(response.reason) + " | Authors: " + str(author_count)
            else:
                status = str(response.status_code) + " | " + str(response.reason)
            dataToSend["nodetuples"].append((node, status))
        except Exception as e:
            print("ERROR checking node", node.url, ":", str(e))
            dataToSend["nodetuples"].append((node, f"Error: {str(e)}"))

    return render(request, "social_distribution/nodes.html", dataToSend)

# API CALLABLE
@csrf_exempt    
@api_view(['POST'])
def loginregister(request):
    username = request.POST["username"]
    password = request.POST["password"]
    node_host = f"{request.scheme}://{request.get_host()}"
    user = authenticate(request, username=username, password=password)

    if user is not None:
        validate_create_author(username, node_host)
        author = Author.objects.get(username=username)
        if not author.is_approved:
            return render(request, 'login.html', {'message': 'Your account is pending admin approval.'})
        login(request, user)
        return redirect("/social_distribution")
    else:
        if not author_exists(username):
            try:
                User.objects.create_user(username=username, password=password)
                validate_create_author(username, node_host)
                return render(request, 'login.html', {
                    'message': f'Account created for {username}. Waiting for admin approval.'
                    })
            except Exception as ex:
                return render(request, 'login.html', {'message': str(ex)})
        return render(request, 'login.html', {'message': 'Invalid username or password'})

@csrf_exempt
@login_required
@api_view(['POST'])
def signout(request):
    logout(request._request)
    return redirect("/social_distribution")

@csrf_exempt
@login_required
@api_view(['POST'])
def editprofile(request):
    author = get_current_author(request)
    form = ChangeProfileForm(request.data)
    if form.is_valid():
        author.name = form.cleaned_data['name']
        if form.cleaned_data['description']:
            author.description = form.cleaned_data['description']
        if form.cleaned_data['picture']:
            author.picture = form.cleaned_data['picture']
        if form.cleaned_data['github']:
            author.github = form.cleaned_data['github']
        author.save()
        return redirect("/social_distribution")
    
    return render(request, 'changeprofile.html', {'message': 'Form requirements failed, change failed.'})

@csrf_exempt
@login_required
def addentry(request):
    if request.method != 'POST': 
        return redirect("/social_distribution")

    author = get_current_author(request)
    title = request.POST.get('title', '')
    content = request.POST.get('content','')
    description = request.POST.get('description', '')
    content_type = request.POST.get('content_type','text/plain')
    visibility = request.POST.get('visibility', 'PUBLIC')

    if 'image' in request.FILES:
        image_file = request.FILES['image']
        image_data = base64.b64encode(image_file.read()).decode('utf-8')
        mime = image_file.content_type
        content = image_data
        base_mime = mime.split(';')[0].strip()
        content_type = f"{base_mime};base64"

    if not title.strip():
        if content_type.startswith('image/'):
            title = 'Image post'
        else:
            title = content[:80] + ('...' if len(content) > 80 else '')

    entry = TextEntry.objects.create(
        author=author,
        title=title,
        description=description,
        content=content,
        content_type=content_type,
        visibility=visibility,
        source_type='native',
    )
    #push to remote follower inboxes 
    send_entry_to_followers(entry, request)

    return redirect("/social_distribution")


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


@login_required
def follow_requests(request):
    author = get_current_author(request)
    requests = Follow.objects.filter(
        following =author,
        approved = False
    )
    return render(request, "social_distribution/follow_requests.html", {"requests": requests})


@login_required
def follow_author(request, username):
    if request.method != 'POST':
        return redirect("social_distribution:profile", username=username)
    current_author = get_current_author(request)
    target_author = get_object_or_404(Author, username=username)

    if current_author != target_author:
        follow, created = Follow.objects.get_or_create(
            follower=current_author,
            following=target_author,
            defaults={"approved": False}
        )
        if created and not target_author.is_local:
                send_follow_to_inbox(follow, request)

    return redirect("social_distribution:profile", username=username)



@login_required
def follow_by_serial(request, serial):
    if request.method != 'POST':
        return redirect("social_distribution:index")
    current_author = get_current_author(request)
    target_author = get_object_or_404(Author, serial=serial)

    if current_author != target_author:
        follow, created = Follow.objects.get_or_create(
            follower=current_author,
            following=target_author,
            defaults={"approved": False}
        )
        if created and not target_author.is_local:
            send_follow_to_inbox(follow, request)

    return redirect("social_distribution:author_list")


@login_required
def approve_follow(request, serial):
    current_author = get_current_author(request)
    follower_author = get_object_or_404(Author, serial=serial)
    follow = get_object_or_404(Follow, follower=follower_author, following=current_author)
    follow.approved = True
    follow.save()
    return redirect("social_distribution:follow_requests")


@login_required
def reject_follow(request, serial):
    current_author = get_current_author(request)
    follower_author = get_object_or_404(Author, serial=serial)
    Follow.objects.filter(
        follower=follower_author,
        following=current_author,
        approved=False
    ).delete()
    return redirect("social_distribution:follow_requests")

@login_required
def unfollow(request, username):
    if request.method != 'POST':
        return redirect("social_distribution:index")
    current_author = get_current_author(request)
    target_author = get_object_or_404(Author, username=username)
    Follow.objects.filter(
        follower=current_author,
        following =target_author
    ).delete()
    return redirect("social_distribution:index")

@login_required
def author_list(request):
    current_author = get_current_author(request)

    # Refresh known remote authors from enabled nodes so users can follow them.
    for node in Node.objects.filter(is_enabled=True):
        try:
            remote_node_get_authors(node, auth_required=False)
        except Exception:
            continue

    authors = Author.objects.exclude(serial=current_author.serial)
    
    following_ids = set(
        Follow.objects.filter(follower=current_author).values_list('following_id', flat=True)
    )
    for author in authors:
        author.is_followed = author.id in following_ids
    
    return render(request, "social_distribution/author_list.html",{"authors": authors})

@login_required
def followers_list(request):
    current_author = get_current_author(request)

    followers = Follow.objects.filter(
        following=current_author,
        approved=True
    ).select_related('follower')

    return render(request, "social_distribution/followers_list.html", {"followers": followers, "author": current_author})

@login_required
def following_list(request):
    current_author = get_current_author(request)

    following = Follow.objects.filter(
        follower=current_author,
        approved=True
    ).select_related('following')

    return render(request, "social_distribution/following_list.html", {"following": following, "author": current_author})



@login_required
def friends_list(request):
    current_author = get_current_author(request) 
    
    # authors who current_author follows
    following_ids = Follow.objects.filter(
        follower=current_author, approved=True
    ).values_list('following_id', flat=True)
    
    # of those, who also follows current_author back
    all_friends = Author.objects.filter(id__in=following_ids).filter(
        following__following=current_author,
        following__approved=True
        ).distinct()
    return render(request, "social_distribution/friends_list.html", {"friends_list": all_friends})


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

@csrf_exempt
@api_view(['GET', 'POST'])
def api_author_entries(request, author_serial):
    target_author = get_object_or_404(Author, serial=author_serial)

    if request.method == 'GET':
        from .utils import authenticate_remote_node
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