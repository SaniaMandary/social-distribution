from django.utils import timezone
import markdown
import logging
import requests as http_requests
from django.shortcuts import render, get_object_or_404, redirect
from django.views import generic
from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from .forms import TextEntryForm
from .models import Like, TextEntry, Author, Follow, Comment
from .forms import ChangeProfileForm
from .serializers import EntrySerializer, AuthorSerializer, LikeSerializer, CommentSerializer
from django.http import FileResponse

# VIEWS
logger = logging.getLogger(__name__)

def index(request):
    if request.user.is_authenticated:
        # authenticated personal page view
        author = Author.objects.get(pk=request.user.username)

        # author's own entries
        entries = TextEntry.objects.filter(
            belonging_url=request.user.username,
            is_deleted=False
        ).order_by("-pub_date")

        # stream: entries from authors you follow
        followfriends_entries = None
        people_you_follow = Follow.objects.filter(follower=author, approved=True)

        for follow in people_you_follow:
            following_author = follow.following

            # everyone you follow: public entries
            following_entries = TextEntry.objects.filter(
                belonging_url=following_author.url,
                visibility="PUBLIC",
                is_deleted=False
            )
            # everyone you follow: unlisted entries
            following_entries = following_entries.union(
                TextEntry.objects.filter(
                    belonging_url=following_author.url,
                    visibility="UNLISTED",
                    is_deleted=False
                )
            )
            # friends only: friends-only entries
            if friends(author, following_author):
                following_entries = following_entries.union(
                    TextEntry.objects.filter(
                        belonging_url=following_author.url,
                        visibility="FRIENDS",
                        is_deleted=False
                    )
                )

            if followfriends_entries is None:
                followfriends_entries = following_entries
            else:
                followfriends_entries = followfriends_entries.union(following_entries)

        if followfriends_entries is not None:
            followfriends_entries = followfriends_entries.order_by("-pub_date")

        # all public entries on the node
        public_entries = TextEntry.objects.filter(
            visibility="PUBLIC",
            is_deleted=False
        ).order_by("-pub_date")
        
        # Apply markdown to all entries if they exist
        #I should refactor this code in some othe function and then call it here. Maybe a utils.py ?  
        for entry in entries or []:
            if entry.content_type == 'text/markdown':
                entry.content_rendered = markdown.markdown(entry.entry_text)
                entry.header_rendered = markdown.markdown(entry.entry_header)

        for followEntry in followfriends_entries or []:
            if followEntry.content_type == 'text/markdown':
                followEntry.content_rendered = markdown.markdown(followEntry.entry_text)
                followEntry.header_rendered = markdown.markdown(followEntry.entry_header)

        for pubEntry in public_entries or []:
            if pubEntry.content_type == 'text/markdown':
                pubEntry.content_rendered = markdown.markdown(pubEntry.entry_text)
                pubEntry.header_rendered = markdown.markdown(pubEntry.entry_header)    

        return render(request, "social_distribution/index.html", {
            'latest_entry_list': entries,
            'following_entry_stream': followfriends_entries,
            'all_public_entries': public_entries,
            'author': author.name,
            'picture_url': author.picture,
            'public_url': author.url,
        })
    else:
        # redirect for login
        return redirect('/social_distribution/login')

def profile_view(request, username):
    author = get_object_or_404(Author, pk=username)
    fetch_github_entries(author) 

    current_author = None
    if request.user.is_authenticated:
        current_author = Author.objects.get(pk=request.user.username)

    is_own_profile = current_author == author if current_author else False

    entry_filter = Q(visibility='PUBLIC')

    if is_own_profile:
        # owner sees all their own entries
        entry_filter |= Q(visibility='FRIENDS') | Q(visibility='UNLISTED')
    elif current_author:
        if friends(current_author, author):
            entry_filter |= Q(visibility='FRIENDS')
    
    entries = TextEntry.objects.filter(
        belonging_url=username,
        is_deleted=False,
    ).filter(entry_filter).order_by("-pub_date")

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

    entries_dictionary = {
        'latest_entry_list' : entries,
        'author' : author.name,
        'author_username': author.url,
        'picture_url' : author.picture,
        'is_following': is_following,
        'is_follow_requested': is_follow_requested,
        'is_own_profile': is_own_profile
    }

    return render(request, "social_distribution/publicprofile.html", entries_dictionary)

class DetailView(generic.DetailView):
    model = TextEntry
    context_object_name = "entry"
    template_name = "social_distribution/detail.html"

    def get_context_data(self, **kwargs): 
        context = super().get_context_data(**kwargs)
        entry = context['entry']
        user = self.request.user

        author_entry_belongs_to = Author.objects.get(pk=entry.belonging_url)

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
                viewer = Author.objects.get(pk=user.username)
                is_owner = viewer == author_entry_belongs_to
                context['is_visible'] = is_owner or friends(viewer, author_entry_belongs_to)

        else:
            context['is_visible'] = False

        # markdown rendering
        if entry.content_type == 'text/markdown': 
            entry.content_rendered = markdown.markdown(entry.entry_text)
            entry.header_rendered = markdown.markdown(entry.entry_header)

        liked_object = f"{self.request.scheme}://{self.request.get_host()}/social_distribution/entries/{entry.id}"
        context['likes_count'] = Like.objects.filter(object=liked_object).count()
        
        # Check if user has liked this entry
        if user.is_authenticated:
            context['has_liked'] = Like.objects.filter(author__pk=user.username, object=liked_object).exists()
        else:
            context['has_liked'] = False
        
        # Get all comments for this entry
        comments = Comment.objects.filter(entry=entry).order_by('-created_at')
        # annotate like counts and whether current user liked each comment
        comment_list = []
        for comment in comments:
            comment.likes_count = Like.objects.filter(
                object=f"{self.request.scheme}://{self.request.get_host()}/social_distribution/comments/{comment.pk}"
            ).count()
            if user.is_authenticated:
                comment.user_liked = Like.objects.filter(
                    author__pk=user.username,
                    object=f"{self.request.scheme}://{self.request.get_host()}/social_distribution/comments/{comment.pk}"
                ).exists()
            else:
                comment.user_liked = False
            comment_list.append(comment)
        context['comments'] = comment_list

        return context 

def login_view(request):
    if request.user.is_authenticated:
        # if authenticated, redirect to index
        return redirect("/social_distribution")
    else:
        # if not logged in, render the login page
        return render(request, "login.html")

@login_required(login_url='/social_distribution/login')
def newentry_view(request):
    form = TextEntryForm()
    return render(request, "social_distribution/newentry.html", {'form': form})

@login_required(login_url='/social_distribution/login')
def changeprofile_view(request):
    author = Author.objects.get(pk=request.user.username)
    return render(request, "changeprofile.html", 
                  {'name' : author.name, 'description' : author.description, 'picture' : author.picture, 'github' : author.github })


# API CALLABLE

def author_exists(username):
    return Author.objects.filter(url=username).exists()
def validate_create_author(username, node_host):
    if author_exists(username):
        return
    author = Author(url=username, name=username, host=node_host, is_local=True)
    author.save()
    
@api_view(['POST'])
def loginregister(request):
    username = request.POST["username"]
    password = request.POST["password"]
    node_host = f"{request.scheme}://{request.get_host()}"
    user = authenticate(request, username=username, password=password)

    if user is not None:
        validate_create_author(username, node_host)
        author = Author.objects.get(pk=username)
        if not author.is_approved:
            return render(request, 'login.html', {'message': 'Your account is pending admin approval.'})
        login(request, user)
        return redirect("/social_distribution")
    else:
        if not author_exists(username):
            try:
                user = User.objects.create_user(username=username, password=password)
                validate_create_author(username, node_host)
                return render(request, 'login.html', {'message': 'Account created for ' + str(username) + '. Waiting for admin approval.'})
            except Exception as ex:
                return render(request, 'login.html', {'message': str(ex)})

        return render(request, 'login.html', {'message': 'Invalid username or password'})

@login_required
@api_view(['POST'])
def signout(request):
    logout(request._request)
    return redirect("/social_distribution")

@login_required
@api_view(['POST'])
def editprofile(request):
    author = Author.objects.get(pk=request.user.username)

    commentForm = ChangeProfileForm(request.data)
    if commentForm.is_valid():
        author.name = commentForm.cleaned_data['name']
        if commentForm.cleaned_data['description']:
            author.description = commentForm.cleaned_data['description']
        if commentForm.cleaned_data['picture']:
            author.picture = commentForm.cleaned_data['picture']
        if commentForm.cleaned_data['github']:
            author.github = commentForm.cleaned_data['github']
        author.save()
        return redirect("/social_distribution")
    
    return render(request, 'changeprofile.html', {'message': 'Form requirements failed, change failed.'})

@login_required
@api_view(['POST'])
def addentry(request):
    author = Author.objects.get(pk=request.user.username)

    data = {'belonging_url': author.url,
            'entry_text': request.data.get('entry_text',''),
            'entry_header': request.data.get('entry_header', ''),
            'content_type': request.data.get('content_type','text/plain'),
            'visibility': request.data.get('visibility', 'PUBLIC'),
            'source_type': 'native',   
        }
    
    if not data['entry_header'].strip(): 
        text = data['entry_text']
        data['entry_header'] = text[:80] + ('...' if len(text) > 80 else '')
    
    if 'image' in request.FILES:
        data['image'] = request.FILES['image']


    serializer = EntrySerializer(data=data, context={'request': request})

    # success
    if serializer.is_valid():
        serializer.save()
        return redirect("/social_distribution")
    
    # failure
    return Response(serializer.errors, status=400)

@api_view(['GET'])
def get_entries(request):
    """
    Get the list of entries on our node
    """
    entries = TextEntry.objects.filter(is_deleted=False)
    serializer = EntrySerializer(entries, many=True, context={'request': request})
    return Response(serializer.data)

@login_required
@api_view(['DELETE'])
def deleteentry(request, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id, belonging_url=request.user.username, is_deleted=False)
    entry.is_deleted = True
    entry.save()
    return Response({"success": True, "message": "Entry deleted."}, status=200)

@login_required
@api_view(['PUT'])
def editentry(request, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id, belonging_url=request.user.username, is_deleted=False)
    new_text = request.data.get('entry_text', '').strip()
    new_content_type = request.data.get('content_type', '').strip()
    new_visibility = request.data.get('visibility', '').strip()

    if not new_text:
        return Response({"error": "entry_text is required and cannot be empty."}, status=400)

    entry.entry_text = new_text
    if new_content_type in ['text/plain', 'text/markdown']:
        entry.content_type = new_content_type
    if new_visibility in ['PUBLIC', 'FRIENDS', 'UNLISTED']:
        entry.visibility = new_visibility
    entry.save()

    serializer = EntrySerializer(entry, context={'request': request})
    return Response(serializer.data, status=200)

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

@api_view(['GET'])
def get_likes(request, object_id):
    likes = Like.objects.filter(object=object_id).order_by('-published')
    serializer = LikeSerializer(likes, many=True, context={'request': request})

    return Response({
        "type": "likes",
        "id": f"{object_id}/likes",
        "web": f"{object_id}/likes",
        "page_number": 1,
        "size": len(serializer.data),
        "count": len(serializer.data),
        "src": serializer.data
    })

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
    author = Author.objects.get(pk=request.user.username)

    requests = Follow.objects.filter(
        following =author,
        approved = False
    )

    return render(request, "social_distribution/follow_requests.html", {"requests": requests})

@login_required
def follow_author(request, username):
    if request.method != 'POST':
        return redirect("social_distribution:profile", username=username)
    current_author = Author.objects.get(pk=request.user.username)
    target_author = get_object_or_404(Author, pk=username)

    if current_author != target_author:
        Follow.objects.get_or_create(
            follower=current_author,
            following=target_author,
            defaults={"approved": False}
        )
    return redirect("social_distribution:profile", username=username)

@login_required
def approve_follow(request, username):
    current_author = Author.objects.get(pk=request.user.username)
    follower_author = get_object_or_404(Author, pk=username)

    follow = get_object_or_404(Follow, follower=follower_author, following=current_author)

    follow.approved = True
    follow.save()

    return redirect("social_distribution:follow_requests")

@login_required
def reject_follow(request, username):
    current_author = Author.objects.get(pk=request.user.username)
    follower_author = get_object_or_404(Author, pk=username)

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
    current_author = Author.objects.get(pk=request.user.username)
    target_author = get_object_or_404(Author, pk=username)

    Follow.objects.filter(
        follower=current_author,
        following =target_author
    ).delete()

    return redirect("social_distribution:index")

@login_required
def author_list(request):
    current_author = Author.objects.get(pk=request.user.username)
    authors = Author.objects.exclude(url=current_author.url)
    return render(request, "social_distribution/author_list.html",{"authors": authors})

@login_required
def followers_list(request):
    current_author = Author.objects.get(pk=request.user.username)

    followers = Follow.objects.filter(
        following=current_author,
        approved=True
    ).select_related('follower')

    return render(request, "social_distribution/followers_list.html", {"followers": followers, "author": current_author})

@login_required
def following_list(request):
    current_author = Author.objects.get(pk=request.user.username)

    following = Follow.objects.filter(
        follower=current_author,
        approved=True
    ).select_related('following')

    return render(request, "social_distribution/following_list.html", {"following": following, "author": current_author})

def friends(author1, author2):
    return(
        Follow.objects.filter(
            follower=author1,
            following=author2,
            approved=True
        ).exists()
        and
        Follow.objects.filter(
            follower=author2,
            following=author1,
            approved=True
        ).exists()
    )

@login_required
def friends_list(request):
    current_author = Author.objects.get(pk=request.user.username)
    
    # authors who current_author follows
    following_ids = Follow.objects.filter(
        follower=current_author, approved=True
    ).values_list('following_id', flat=True)
    
    # of those, who also follows current_author back
    all_friends = Author.objects.filter(url__in=following_ids).filter(
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
        Author.objects.get(pk=username)
        entry = TextEntry.objects.get(pk=entry_id, belonging_url=username, is_deleted=False)

        if not request.user.is_authenticated or request.user.username != username:
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
        Author.objects.get(pk=username)
        entry = TextEntry.objects.get(pk=entry_id, belonging_url=username, is_deleted=False)

        if not request.user.is_authenticated or request.user.username != username:
            return Response({"error": "You must be logged in as the entry owner to edit it."}, status=403)

        new_text = request.data.get('entry_text', '').strip()
        new_content_type = request.data.get('content_type', '').strip()
        new_visibility = request.data.get('visibility', '').strip()

        if not new_text:
            return Response({"error": "entry_text is required and cannot be empty."}, status=400)

        entry.entry_text = new_text
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

@api_view(['GET', 'PUT', 'DELETE'])
def api_entry_detail(request, entry_id):
    """
    GET    /api/entries/{entry_id}/  - retrieve a single entry (respects visibility)
    PUT    /api/entries/{entry_id}/  - update entry (owner only)
    DELETE /api/entries/{entry_id}/  - soft-delete entry (owner only)
    """
    entry = get_object_or_404(TextEntry, id=entry_id, is_deleted=False)

    if request.method == 'GET':
        if entry.visibility == 'FRIENDS':
            if not request.user.is_authenticated:
                return Response({"error": "Authentication required to view a friends-only entry."}, status=403)
            viewer = Author.objects.get(pk=request.user.username)
            entry_author = Author.objects.get(pk=entry.belonging_url)
            if viewer != entry_author and not friends(viewer, entry_author):
                return Response({"error": "You are not friends with this author."}, status=403)
        serializer = EntrySerializer(entry, context={'request': request})
        return Response(serializer.data)

    if not request.user.is_authenticated:
        return Response({"error": "Authentication required."}, status=403)
    if request.user.username != entry.belonging_url:
        return Response({"error": "You do not own this entry."}, status=403)

    if request.method == 'PUT':
        new_text = request.data.get('entry_text', '').strip()
        new_content_type = request.data.get('content_type', '').strip()
        new_visibility = request.data.get('visibility', '').strip()

        if not new_text:
            return Response({"error": "entry_text is required and cannot be empty."}, status=400)

        entry.entry_text = new_text
        if new_content_type in ['text/plain', 'text/markdown']:
            entry.content_type = new_content_type
        if new_visibility in ['PUBLIC', 'FRIENDS', 'UNLISTED']:
            entry.visibility = new_visibility
        entry.save()

        serializer = EntrySerializer(entry, context={'request': request})
        return Response(serializer.data, status=200)

    if request.method == 'DELETE':
        entry.is_deleted = True
        entry.save()
        return Response({"success": True, "message": "Entry deleted."}, status=200)


@api_view(['GET'])
def api_authors(request):
    page_number = int(request.query_params.get('page', 1))
    size = int(request.query_params.get('size', 10))
    all_authors = Author.objects.all().order_by('url')
    total = all_authors.count()
    start = (page_number - 1) * size
    end = start + size
    serializer = AuthorSerializer(all_authors[start:end], many=True, context={'request': request})
    return Response({
        "type": "authors",
        "page_number": page_number,
        "size": size,
        "count": total,
        "authors": serializer.data
    })


@api_view(['GET'])
def api_author_followers(request, username):
    author = get_object_or_404(Author, pk=username)
    follows = Follow.objects.filter(following=author, approved=True).select_related('follower')
    serializer = AuthorSerializer([f.follower for f in follows], many=True, context={'request': request})
    return Response({"type": "followers", "followers": serializer.data})


@api_view(['GET'])
def api_author_following(request, username):
    author = get_object_or_404(Author, pk=username)
    follows = Follow.objects.filter(follower=author, approved=True).select_related('following')
    serializer = AuthorSerializer([f.following for f in follows], many=True, context={'request': request})
    return Response({"type": "following", "following": serializer.data})

@api_view(['GET'])
def get_entry_image(request, username, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id, belonging_url=username, is_deleted=False)

    # return 404 if this entry is not an image
    if not entry.image:
        return Response({"error": "This entry does not have an image."}, status=404)

    # friends-only image entries require authentication and friendship
    if entry.visibility == "FRIENDS":
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required."}, status=403)
        viewer = Author.objects.get(pk=request.user.username)
        entry_author = Author.objects.get(pk=username)
        if viewer != entry_author and not friends(viewer, entry_author):
            return Response({"error": "You are not friends with this author."}, status=403)
        
    return FileResponse(entry.image.open('rb'), content_type=entry.content_type)

#

def fetch_github_entries(author): 
    if not author.github: 
        logger.warning(f"No github URL for {author.url}")
        return 
    
    github_username = author.github.rstrip('/').split('/')[-1]
    if not github_username:
        logger.warning(f"Could not parse github username from: {author.github}")
        return
    
    try:
        response = http_requests.get(
            f"https://api.github.com/users/{github_username}/events/public",
            timeout=5,
            headers={"Accept": "application/vnd.github+json"}
        )
        if response.status_code != 200:
             logger.warning(f"GitHub API returned {response.status_code} for {github_username}")
             return
        events = response.json()
        logger.info(f"Fetched {len(events)} events for {github_username}")
    except Exception as e:
        logger.error(f"GitHub fetch failed: {e}")
        return

    last_polled = author.github_last_polled
    new_entries = []

    for event in events:
        # parse the event timestamp
        try:
            from datetime import datetime, timezone as dt_tz
            event_time = datetime.strptime(
                event.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=dt_tz.utc)
        except Exception:
            continue
        
        if last_polled and event_time <= last_polled:
            continue

        event_type = event.get("type", "")
        repo_name = event.get("repo", {}).get("name", "unknown/repo")
        payload = event.get("payload", {})
        
        if event_type == "PushEvent":
            commits = payload.get("commits", [])
            messages = [c.get("message", "") for c in commits[:3]]
            description = f"Pushed {len(commits)} commit(s) to [{repo_name}](https://github.com/{repo_name}):\n"
            description += "\n".join(f"- {m}" for m in messages)

        elif event_type == "CreateEvent":
            ref_type = payload.get("ref_type", "repository")
            ref = payload.get("ref", "")
            description = f"Created {ref_type} `{ref}` in [{repo_name}](https://github.com/{repo_name})"

        elif event_type == "IssuesEvent":
            action = payload.get("action", "")
            issue = payload.get("issue", {})
            title = issue.get("title", "")
            issue_url = issue.get("html_url", "")
            description = f"{action.capitalize()} issue [{title}]({issue_url}) in [{repo_name}](https://github.com/{repo_name})"

        elif event_type == "PullRequestEvent":
            action = payload.get("action", "")
            pr = payload.get("pull_request", {})
            title = pr.get("title", "")
            pr_url = pr.get("html_url", "")
            description = f"{action.capitalize()} pull request [{title}]({pr_url}) in [{repo_name}](https://github.com/{repo_name})"

        elif event_type == "WatchEvent":
            description = f"Starred [{repo_name}](https://github.com/{repo_name}) ⭐"

        elif event_type == "ForkEvent":
            forkee = payload.get("forkee", {}).get("full_name", "")
            description = f"Forked [{repo_name}](https://github.com/{repo_name}) → [{forkee}](https://github.com/{forkee})"

        else: 
            continue 
        
        new_entries.append(TextEntry(
            belonging_url=author.url,
            entry_text=description,
            content_type='text/markdown',
            visibility='PUBLIC',
            pub_date=event_time,
            source_type='github'
        ))

    if new_entries:
        TextEntry.objects.bulk_create(new_entries)

    author.github_last_polled = timezone.now()
    author.save(update_fields=['github_last_polled'])