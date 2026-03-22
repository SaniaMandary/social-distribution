import base64
import markdown
import logging
import requests as http_requests
#django imports
from django.shortcuts import render, get_object_or_404, redirect
from django.views import generic
from django.db.models import Q
from django.http import HttpResponse
from django.http import FileResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
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
    NOT_DELETED, get_author_by_serial, get_current_author,
    author_exists, validate_create_author, friends,
    fetch_remote_author, can_view_entry, render_markdown_entries,
    get_page_args, paginate_set, build_paginated_response,
    fetch_github_entries, remote_node_get, authenticate_remote_node, 
    send_entry_to_followers, send_follow_to_inbox, send_comment_to_inbox, 
    send_like_to_inbox, send_comment_to_inbox,
)

logger = logging.getLogger(__name__)


# Web-UI Views 
def index(request):
    if not request.user.is_authenticated: # authenticated personal page view
        return redirect('/social_distribution/login')
    
    author = get_current_author(request)
    fetch_github_entries(author, 0) # no cooldown. Refresh always for the logged in user  
    entries = TextEntry.objects.filter(author=author).filter(NOT_DELETED).order_by("-published")

    # stream: entries from authors you follow
    followfriends_entries = None
    people_you_follow = Follow.objects.filter(follower=author, approved=True)

    for follow in people_you_follow:
        following_author = follow.following

        fetch_github_entries(following_author, 1) # enable a cool down for these calls. 

        # everyone you follow: public entries
        following_entries = TextEntry.objects.filter(
            author=following_author,
            visibility="PUBLIC",
        ).filter(NOT_DELETED)

        # everyone you follow: unlisted entries
        following_entries = following_entries.union(
            TextEntry.objects.filter(
                author=following_author,
                visibility="UNLISTED",
            ).filter(NOT_DELETED)
        )

        # friends only: friends-only entries
        if friends(author, following_author):
            following_entries = following_entries.union(
                TextEntry.objects.filter(
                    author=following_author,
                    visibility="FRIENDS",
                ).filter(NOT_DELETED)
            )

        if followfriends_entries is None:
            followfriends_entries = following_entries
        else:
            followfriends_entries = followfriends_entries.union(following_entries)

    if followfriends_entries is not None:
        followfriends_entries = followfriends_entries.order_by("-published")

    # all public entries on the node
    public_entries = TextEntry.objects.filter(visibility="PUBLIC").filter(NOT_DELETED).order_by("-published")
    
    # Apply markdown to all entries if they exist
    #I should refactor this code in some othe function and then call it here. Maybe a utils.py ?  
    render_markdown_entries(entries)
    render_markdown_entries(followfriends_entries)
    render_markdown_entries(public_entries)   

    return render(request, "social_distribution/index.html", {
        'latest_entry_list': entries,
        'following_entry_stream': followfriends_entries,
        'all_public_entries': public_entries,
        'author': author.name,
        'picture_url': author.picture,
        'public_url': author.username,
    })
    


def profile_view(request, username):
    author = get_object_or_404(Author, username=username)
    fetch_github_entries(author, 0) # no cooldown 

    current_author = None
    if request.user.is_authenticated:
        current_author = get_current_author(request)

    is_own_profile = current_author == author if current_author else False

    entry_filter = Q(visibility='PUBLIC')
    if is_own_profile:
        # owner sees all their own entries
        entry_filter |= Q(visibility='FRIENDS') | Q(visibility='UNLISTED')
    elif current_author:
        if friends(current_author, author):
            entry_filter |= Q(visibility='FRIENDS')
    
    entries = TextEntry.objects.filter(author=author).filter(NOT_DELETED).filter(entry_filter).order_by("-published")

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

    def get_context_data(self, **kwargs): 
        context = super().get_context_data(**kwargs)
        entry = context['entry']
        user = self.request.user

        # deleted entries are never visible
        if entry.is_deleted:
            context['is_visible'] = False
        # public and unlisted entries are always visible via link
        elif entry.visibility in ("PUBLIC", "UNLISTED"):
            context['is_visible'] = True
        # friends-only: need to be authenticated and be a friend (or the owner)
        elif entry.visibility == "FRIENDS":
            if not user.is_authenticated:
                context['is_visible'] = False
            else:
                viewer = get_author_by_serial(user.username)
                context['is_visible'] = (viewer == entry.author) or friends(viewer, entry.author)

        else:
            context['is_visible'] = False

        # markdown rendering
        if entry.content_type == 'text/markdown': 
            entry.content_rendered = markdown.markdown(entry.content)
            entry.header_rendered = markdown.markdown(entry.title)

        context['likes_count'] = Like.objects.filter(object_url=entry.fqid).count()
        
        # Check if user has liked this entry
        if user.is_authenticated:
            context['has_liked'] = Like.objects.filter(author__username=user.username, object_url=entry.fqid).exists()
        else:
            context['has_liked'] = False
        
        # Get all comments for this entry
        comments = Comment.objects.filter(local_entry=entry).order_by('-published')
        # annotate like counts and whether current user liked each comment
        comment_list = []
        for comment in comments:
            comment.likes_count = Like.objects.filter(object_url=comment.fqid).count()
            if user.is_authenticated:
                comment.user_liked = Like.objects.filter(author__username=user.username, object_url=comment.fqid).exists()
            else:
                comment.user_liked = False
            comment_list.append(comment)
        context['comments'] = comment_list

        return context 

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
            author_count = response.json().get("count", "N/A") if response.status_code == 200 else "N/A"
            status = str(response.status_code) + " | " + str(response.reason) + " | Authors: " + str(author_count)
            dataToSend["nodetuples"].append((node, status))
            print(f"Checked node {node.url}: {response.status_code}")
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
    
    image_file = None
    if 'image' in request.FILES:
        image_file = request.FILES['image']
        image_data = base64.b64encode(image_file.read()).decode('utf-8')
        mime = image_file.content_type
        content = image_data
        content_type = f"{mime};base64" if 'base64' not in mime else mime

    if not title.strip():
        title = content[:80] + ('...' if len(content) > 80 else '')
    
    entry = TextEntry.objects.create(
        author=author,
        title=title,
        description=description,
        content=content,
        image=image_file,
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
@login_required
@api_view(['DELETE'])
def deleteentry(request, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id, belonging_url=request.user.username, is_deleted=False)
    entry.is_deleted = True
    print(entry.is_deleted)
    entry.save()
    return Response({"success": True, "message": "Entry deleted."}, status=200)

@csrf_exempt
@login_required
@api_view(['PUT'])
def editentry(request, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id, belonging_url=request.user.username, is_deleted=False)
    new_text = request.data.get('content', '').strip()
    new_content_type = request.data.get('content_type', '').strip()
    new_visibility = request.data.get('visibility', '').strip()

    if not new_text:
        return Response({"error": "content is required and cannot be empty."}, status=400)

    entry.content = new_text
    if new_content_type in ['text/plain', 'text/markdown']:
        entry.content_type = new_content_type
    if new_visibility in ['PUBLIC', 'FRIENDS', 'UNLISTED']:
        entry.visibility = new_visibility
    entry.save()

    serializer = EntrySerializer(entry, context={'request': request})
    return Response(serializer.data, status=200)

@csrf_exempt
@login_required
@api_view(['POST'])
def add_like(request):
    author = Author.objects.get(pk=request.user.username)
    liked_object = request.data.get('object', None)

    if not liked_object:
        return Response({"error": "Missing object field"}, status=400)

    like = Like.objects.create(author=author, object=liked_object)
    serializer = LikeSerializer(like, context={'request': request})
    return Response(serializer.data)

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
        result["web"] = f"{entry.author.host}/authors/{entry.author.serial}/entries/{entry.pk}"
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
        return Response(LikeSerializer(like, context={'request': request}).data, status=201)


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
                result["web"] = f"{comment.author.host}/authors/{comment.author.serial}/comments/{comment.pk}/likes"
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
                return Response(LikeSerializer(like, context={'request': request}).data, status=201)

    return Response({"error": "Comment not found."}, status=404)


@csrf_exempt
@login_required
@api_view(['POST'])
def add_like_entry(request, entry_id):
    get_object_or_404(TextEntry, id=entry_id, is_deleted=False)
    author = Author.objects.get(pk=request.user.username)

    liked_object = f"{request.scheme}://{request.get_host()}/social_distribution/entries/{entry_id}"

    existing_like = Like.objects.filter(
        author=author,
        object=liked_object
    ).first()

    if existing_like:
        existing_like.delete()
        return Response({
            "success": True,
            "liked": False,
        })

    Like.objects.create(
        author=author,
        object=liked_object
    )

    return Response({
        "success": True,
        "liked": True,
    })

@csrf_exempt
@login_required
@api_view(['POST'])
def add_like_comment(request, comment_id):
    author = Author.objects.get(pk=request.user.username)
    liked_object = f"{request.scheme}://{request.get_host()}/social_distribution/comments/{comment_id}"

    existing_like = Like.objects.filter(
        author=author,
        object=liked_object
    ).first()

    if existing_like:
        existing_like.delete()
        return Response({
            "success": True,
            "liked": False,
        })

    Like.objects.create(
        author=author,
        object=liked_object
    )
    return Response({
        "success": True,
        "liked": True,
    })


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
def approve_follow(request, username):
    current_author = get_current_author(request)
    follower_author = get_object_or_404(Author, serial=username)
    follow = get_object_or_404(Follow, follower=follower_author, following=current_author)
    follow.approved = True
    follow.save()
    return redirect("social_distribution:follow_requests")



@login_required
def reject_follow(request, username):
    current_author = get_current_author(request)
    follower_author = get_object_or_404(Author, serial=username)
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



@api_view(['GET'])
def get_comments(request, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id, is_deleted=False)

    if entry.visibility == "FRIENDS":
        if not request.user.is_authenticated:
            return Response("You must be logged in to view comments on friends-only entries.", status=403)
        viewer = Author.objects.get(pk=request.user.username)
        entry_author = Author.objects.get(pk=entry.belonging_url)
        if viewer != entry_author and not friends(viewer, entry_author):
            return Response("You are not friends with this author.", status=403)

    comments = Comment.objects.filter(entry__id=entry_id).order_by('-created_at')
    serializer = CommentSerializer(comments, many=True, context={'request': request})

    return Response({
        "type": "comments",
        "id": f"/entries/{entry_id}/comments",
        "web": f"/entries/{entry_id}/comments",
        "page_number": 1,
        "size": len(serializer.data),
        "count": len(serializer.data),
        "src": serializer.data
    })

@csrf_exempt
@login_required
@api_view(['POST'])
def post_entry_comment(request, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id)
    if entry.visibility == "FRIENDS":
        viewer = Author.objects.get(pk=request.user.username)
        entry_author = Author.objects.get(pk=entry.belonging_url)
        if viewer != entry_author and not friends(viewer, entry_author):
            return Response({"error": "You are not friends with this author."}, status=403)
        
    author = Author.objects.get(pk=request.user.username)
    content = request.data.get("comment", "").strip()
    if not content:
        return Response({"error": "Missing comment content"}, status=400)

    comment = Comment.objects.create(
        author=author,
        entry=entry,
        content=content,
        content_type=request.data.get("contentType", "text/markdown")
    )
    serializer = CommentSerializer(comment, context={'request': request})
    return Response(serializer.data, status=201)



# Entries Public API
def entry_get_response(request, username, entry_id):
    # GET case for entry api request
    try:
        target_author = Author.objects.get(pk=username)
        entry = TextEntry.objects.get(pk=entry_id, belonging_url=username, is_deleted=False)

        # consider the case that the entry is friends only
        if entry.visibility == "FRIENDS":
            if request.user.is_authenticated==False:
                return Response("You must be logged in to access friends only entries." ,status=403)
            else:
                try:
                    me = Author.objects.get(pk=request.user.username)
                    if me != target_author and friends(target_author, me) == False:
                        return Response(me.url + " is not friends with " + target_author.url ,status=403)
                except Author.DoesNotExist:
                    return Response("Authenticated author does not exist." ,status=500)

        serializer = EntrySerializer(entry, context={'request': request})
        return Response(serializer.data)
    except TextEntry.DoesNotExist:
        return Response("Entry does not exist." ,status=404)
    except Author.DoesNotExist:
        return Response("Author/user does not exist." ,status=404)

def entry_delete_response(request, username, entry_id):
    try:
        author = get_object_or_404(Author, serial=author_serial)
        entry = get_object_or_404(TextEntry, pk=entry_serial, author=author)

        if not request.user.is_authenticated or request.user.username != author.username:
            return Response({"error": "You must be logged in as the entry owner to delete it."}, status=403)

        entry.is_deleted = True
        entry.save()
        return Response({"success": True, "message": "Entry deleted."}, status=200)
    except TextEntry.DoesNotExist:
        return Response({"error": "Entry does not exist."}, status=404)
    except Author.DoesNotExist:
        return Response({"error": "Author does not exist."}, status=404)
    
def entry_put_response(request, username, entry_id):
    try:
        author = get_object_or_404(Author, serial=author_serial)
        entry = get_object_or_404(TextEntry, pk=entry_serial, author=author)

        if not request.user.is_authenticated or request.user.username != author.username:
            return Response({"error": "You must be logged in as the entry owner to edit it."}, status=403)

        new_text = request.data.get('content', '').strip()
        new_content_type = request.data.get('content_type', '').strip()
        new_visibility = request.data.get('visibility', '').strip()

        if not new_text:
            return Response({"error": "content is required and cannot be empty."}, status=400)

        entry.content = new_text
        if new_content_type in ['text/plain', 'text/markdown']:
            entry.content_type = new_content_type
        if new_visibility in ['PUBLIC', 'FRIENDS', 'UNLISTED']:
            entry.visibility = new_visibility
        entry.save()

        serializer = EntrySerializer(entry, context={'request': request})
        return Response(serializer.data, status=200)
    except TextEntry.DoesNotExist:
        return Response({"error": "Entry does not exist."}, status=404)
    except Author.DoesNotExist:
        return Response({"error": "Author does not exist."}, status=404)
    
@api_view(['GET', 'DELETE', 'PUT'])
def public_user_entry(request, username, entry_id):
    # handle the get delete and put request for entries
    if request.method == 'GET':
        return entry_get_response(request, username, entry_id)
    
    if request.method=='DELETE':
        return entry_delete_response(request,username,entry_id)
    
    if request.method=="PUT":
        return entry_put_response(request,username,entry_id)

@api_view(['GET'])
def public_get_entry(request, entry_id):
    try:
        entry = TextEntry.objects.get(pk=entry_id, is_deleted=False)

        # consider the case that the entry is friends only
        if entry.visibility == "FRIENDS":
            if not request.user.is_authenticated:
                return Response("You must be logged in to access friends only entries.", status=403)
            viewer = Author.objects.get(pk=request.user.username)
            entry_author = Author.objects.get(pk=entry.belonging_url)
            if viewer != entry_author and not friends(viewer, entry_author):
                return Response("You are not friends with this author.", status=403)

        serializer = EntrySerializer(entry, context={'request': request})
        return Response(serializer.data)
    
    except TextEntry.DoesNotExist:
        return Response("Entry does not exist.", status=404)

@csrf_exempt
@api_view(['GET', 'POST'])
def public_user_entries(request, username):
    # get the target author
    try:
        target_author = Author.objects.get(url=username)
    except Author.DoesNotExist:
        return Response("Target author does not exist", 400)

    # handle get request for entries
    if request.method=="GET":
        # return all of the public entries for target user
        if request.user.is_authenticated==False:
            entries = TextEntry.objects.filter(belonging_url=username, visibility="PUBLIC", is_deleted=False).order_by("-pub_date")
            serializer = EntrySerializer(entries, many=True, context={'request': request})
            return Response(serializer.data)
        # authenticated
        else:
            # return all your own entries
            if request.user.username == username:
                entries = TextEntry.objects.filter(belonging_url=username, is_deleted=False).order_by("-pub_date")
                serializer = EntrySerializer(entries, many=True, context={'request': request})
                return Response(serializer.data)
            else:
                request_author = Author.objects.get(pk=request.user.username)
                try:
                    following = Follow.objects.get(follower=request_author, following=target_author, approved=True)

                    # return all entries as a friend
                    if friends(target_author, request_author):
                        entries = TextEntry.objects.filter(belonging_url=username, is_deleted=False).order_by("-pub_date")
                        serializer = EntrySerializer(entries, many=True, context={'request': request})
                        return Response(serializer.data)
                    
                    # return public + unlisted as only a follower
                    entries = TextEntry.objects.filter(belonging_url=username, visibility="PUBLIC", is_deleted=False)
                    entries = entries.union(TextEntry.objects.filter(belonging_url=username, visibility="UNLISTED", is_deleted=False)).order_by("-pub_date")
                    serializer = EntrySerializer(entries, many=True, context={'request': request})
                    return Response(serializer.data)
                except Follow.DoesNotExist:
                    # fall back to returning public entries
                    entries = TextEntry.objects.filter(belonging_url=username, visibility="PUBLIC", is_deleted=False).order_by("-pub_date")
                    serializer = EntrySerializer(entries, many=True, context={'request': request})
                    return Response(serializer.data)
                
    # handle post for creating an entry
    if request.method == "POST":
        if request.user.is_authenticated == False:
            return Response("You must be logged in to create an entry.", 403)
        if request.user.username != username:
            return Response("You must be logged in as the target user to create an entry.", 403)
        
        response = addentry(request)
        return Response("Added entry.", response.status_code)

    pass

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
        local_entry = None
        for e in TextEntry.objects.filter(NOT_DELETED):
            if e.fqid == entry_fqid:
                local_entry = e
                break

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
def api_authors(request):
    page, size = get_page_args(request)
    all_authors = Author.objects.all().order_by('serial')
    total = all_authors.count()
    page_data = paginate_set(all_authors, page, size)
    serializer = AuthorSerializer(page_data, many=True, context={'request': request})
    return Response(build_paginated_response("authors", "authors", serializer.data, page, size, total))

@csrf_exempt
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

@csrf_exempt
@api_view(['GET', 'POST'])
def api_author_entries(request, author_serial):
    target_author = get_object_or_404(Author, serial=author_serial)

    if request.method == 'GET':
        # Visibility logic based on auth status, friendship, follow
        if not request.user.is_authenticated:
            entries = TextEntry.objects.filter(author=target_author, visibility="PUBLIC").filter(NOT_DELETED).order_by("-published")
        elif request.user.username == target_author.username:
            entries = TextEntry.objects.filter(author=target_author).filter(NOT_DELETED).order_by("-published")
        else:
            viewer = get_current_author(request)
            if friends(target_author, viewer):
                entries = TextEntry.objects.filter(author=target_author).filter(NOT_DELETED).order_by("-published")
            elif Follow.objects.filter(follower=viewer, following=target_author, approved=True).exists():
                entries = TextEntry.objects.filter(author=target_author, visibility__in=["PUBLIC", "UNLISTED"]).filter(NOT_DELETED).order_by("-published")
            else:
                entries = TextEntry.objects.filter(author=target_author, visibility="PUBLIC").filter(NOT_DELETED).order_by("-published")

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

    if not title.strip():
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
        
        if 'title' in request.data:       entry.title = request.data['title']
        if 'content' in request.data:     entry.content = request.data['content']
        if 'description' in request.data: entry.description = request.data['description']
        if 'contentType' in request.data:
            ct = request.data['contentType']
            if ct in ['text/plain', 'text/markdown']: entry.content_type = ct
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

    if not request.user.is_authenticated or request.user.username != author.username:
        return Response({"error": "Must be authenticated as this author."}, status=403)

    if request.method == 'GET':
        exists = Follow.objects.filter(
            follower=author, following__id=foreign_author_fqid, approved=True
        ).exists()
        if not exists:
            return Response({"error": "Not following."}, status=404)
        target = Author.objects.get(id=foreign_author_fqid)
        return Response(AuthorSerializer(target, context={'request': request}).data)

    if request.method == 'PUT':
        try:
            target = Author.objects.get(id=foreign_author_fqid)
        except Author.DoesNotExist:
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
        return Response(build_paginated_response("comments", "src", serializer.data, page, size, total))

    if not request.user.is_authenticated or request.user.username != author.username:
        return Response({"error": "Must be authenticated as this author."}, status=403)

    entry_fqid = request.data.get('entry', '')
    comment_text = request.data.get('comment', '').strip()
    content_type = request.data.get('contentType', 'text/markdown')

    if not comment_text: return Response({"error": "Missing comment content."}, status=400)
    if not entry_fqid:   return Response({"error": "Missing entry field."}, status=400)

    local_entry = None
    for e in TextEntry.objects.filter(NOT_DELETED):
        if e.fqid == entry_fqid:
            local_entry = e
            break

    comment = Comment.objects.create(
        author=author, entry=entry_fqid, local_entry=local_entry,
        comment=comment_text, content_type=content_type,
    )

    if local_entry:
        send_comment_to_inbox(comment, local_entry.author, request)
    else:
        # Entry is remote — try to find the author from the entry FQID
        # FQID looks like http://node/api/authors/abc/entries/123
        # We need to find the author whose FQID matches the prefix
        for a in Author.objects.filter(is_local=False):
            if entry_fqid.startswith(a.fqid):
                send_comment_to_inbox(comment, a, request)
                break
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
    for comment in Comment.objects.all():
        if comment.fqid == comment_fqid:
            return Response(CommentSerializer(comment, context={'request': request}).data)
    return Response({"error": "Comment not found."}, status=404)


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
    for like in Like.objects.all():
        if like.fqid == like_fqid:
            return Response(LikeSerializer(like, context={'request': request}).data)
    return Response({"error": "Like not found."}, status=404)

@api_view(['GET'])
def api_entry_fqid(request, entry_fqid):
    for entry in TextEntry.objects.filter(NOT_DELETED):
        if entry.fqid == entry_fqid:
            if not can_view_entry(request, entry):
                return Response({"error": "Entry not accessible."}, status=404)
            return Response(EntrySerializer(entry, context={'request': request}).data)
    return Response({"error": "Entry not found."}, status=404)


api_view(['GET'])
def api_entry_fqid_comments(request, entry_fqid):
    for entry in TextEntry.objects.filter(NOT_DELETED):
        if entry.fqid == entry_fqid:
            if not can_view_entry(request, entry):
                return Response({"error": "Entry not accessible."}, status=404)
            page, size = get_page_args(request, default_size=5)
            comments_qs = Comment.objects.filter(local_entry=entry).order_by('-published')
            total = comments_qs.count()
            page_data = paginate_set(comments_qs, page, size)
            serializer = CommentSerializer(page_data, many=True, context={'request': request})
            result = build_paginated_response("comments", "src", serializer.data, page, size, total)
            result["id"] = f"{entry.fqid}/comments"
            result["web"] = f"{entry.author.host}/authors/{entry.author.serial}/entries/{entry.pk}"
            return Response(result)
    return Response({"error": "Entry not found."}, status=404)


@api_view(['GET'])
def api_entry_fqid_likes(request, entry_fqid):
    for entry in TextEntry.objects.filter(NOT_DELETED):
        if entry.fqid == entry_fqid:
            if not can_view_entry(request, entry):
                return Response({"error": "Entry not accessible."}, status=404)
            page, size = get_page_args(request, default_size=50)
            likes_qs = Like.objects.filter(object_url=entry.fqid).order_by('-published')
            total = likes_qs.count()
            page_data = paginate_set(likes_qs, page, size)
            serializer = LikeSerializer(page_data, many=True, context={'request': request})
            result = build_paginated_response("likes", "src", serializer.data, page, size, total)
            result["id"] = f"{entry.fqid}/likes"
            result["web"] = f"{entry.author.host}/authors/{entry.author.serial}/entries/{entry.pk}"
            return Response(result)
    return Response({"error": "Entry not found."}, status=404)


@api_view(['GET'])
def api_entry_fqid_image(request, entry_fqid):
    for entry in TextEntry.objects.all():
        if entry.fqid == entry_fqid:
            if not can_view_entry(request, entry):
                return Response({"error": "Entry not accessible."}, status=404)
            if not entry.content_type.startswith('image/'):
                return Response({"error": "Not an image entry."}, status=404)
            try:
                image_bytes = base64.b64decode(entry.content)
                mime = entry.content_type.replace(';base64', '')
                return HttpResponse(image_bytes, content_type=mime)
            except Exception:
                return Response({"error": "Could not decode image."}, status=500)
    return Response({"error": "Entry not found."}, status=404)

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
        result["web"] = f"{entry.author.host}/authors/{entry.author.serial}/entries/{entry.pk}"
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
    send_like_to_inbox(like, entry.author, request)
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
