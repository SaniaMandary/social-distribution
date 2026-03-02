from datetime import timezone

import markdown
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views import generic
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required

from .models import Like, TextEntry, Author, Follow, Comment
from .forms import ChangeProfileForm
from .serializers import EntrySerializer, LikeSerializer, CommentSerializer

# VIEWS

def index(request):
    print("Is user authenticated? " + str(request.user.username))

    if request.user.is_authenticated:
        # authenticated personal page view
        author = Author.objects.get(pk=request.user.username)

        entries = TextEntry.objects.filter(belonging_url=request.user.username, is_deleted=False).order_by("-pub_date")

        entries_dictionary = {
            'latest_entry_list' : entries.values(),
            'author' : author.name,
            'picture_url' : author.picture,
            'public_url' : author.url,
            }

        return render(request, "social_distribution/index.html", entries_dictionary)
    else:
        # redirect for login
        return redirect('/social_distribution/login')

def profile_view(request, username):
    author = get_object_or_404(Author, pk=username)

    is_following = Follow.objects.filter(
        follower = author,
        approved = True
    ).values_list("following", flat=True)

    is_own_profile = request.user.username == author.url
    # add required data to render posts
    entries = TextEntry.objects.filter(belonging_url=username, is_deleted=False, visibility='PUBLIC').order_by("-pub_date")

    entries_dictionary = {
        'latest_entry_list' : entries.values(),
        'author' : author.name,
        'picture_url' : author.picture,
        'is_following': is_following,
        'is_own_profile': is_own_profile
        }

    # render the page
    return render(request, "social_distribution/publicprofile.html", entries_dictionary)

class DetailView(generic.DetailView):
    model = TextEntry
    context_object_name = "entry"
    template_name = "social_distribution/detail.html"

    def get_context_data(self, **kwargs): 
        context = super().get_context_data(**kwargs)
        entry = context['entry']

        #redner markdown if content_type is selected as such 
        if entry.content_type == 'text/markdown': 
            entry.content_rendered = markdown.markdown(entry.entry_text)

        user = self.request.user
        liked_object = f"{self.request.scheme}://{self.request.get_host()}/social_distribution/entries/{entry.id}"
        context['likes_count'] = Like.objects.filter(object=liked_object).count()
        context['has_liked'] = Like.objects.filter(author__pk=user.username, object=liked_object).exists()

        return context 

def login_view(request):
    print("Is user authenticated? " + str(request.user.is_authenticated))
    if request.user.is_authenticated:
        # if authenticated, redirect to index
        return redirect("/social_distribution")
    else:
        # if not logged in, render the login page
        return render(request, "login.html")

@login_required(login_url='/social_distribution/login')
def newentry_view(request):
    return render(request, "social_distribution/newentry.html")

@login_required(login_url='/social_distribution/login')
def changeprofile_view(request):
    author = Author.objects.get(pk=request.user.username)
    return render(request, "changeprofile.html", 
                  {'name' : author.name, 'description' : author.description, 'picture' : author.picture, 'github' : author.github })


# API CALLABLE

def author_exists(username):
    return Author.objects.filter(url=username).exists()
def validate_create_author(username):
    # creates author with username if does not already exist
    if author_exists(username):
        return
    
    url = username # THIS DOES NOT CHECK FOR MALICIOUS USERNAMES (/ will fail)
    author = Author(url=url, name = username)
    author.save()
    pass
@api_view(['POST'])
def loginregister(request):
    username = request.POST["username"]
    password = request.POST["password"]
    user = authenticate(request, username=username, password=password)

    # django recognizes the user
    if user is not None:
        login(request, user)
        validate_create_author(username)
        return redirect("/social_distribution")
    # django does not recognize the user
    else:
        if not author_exists(username):
            # automatically register a new user, redirect for login
            try:
                user = User.objects.create_user(username=username, password=password)
            except Exception as ex:
                return render(request, 'login.html', {'message': str(ex)})
            
            return render(request, 'login.html', {'message': 'Created new user ' + str(username)})

        # the user exists, just the password was wrong
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
        # Get username and content from the form
        name = commentForm.cleaned_data['name']
        description = commentForm.cleaned_data['description']
        picture = commentForm.cleaned_data['picture']
        github = commentForm.cleaned_data['github']

        author.name = name
        author.description = description
        author.picture = picture
        author.github = github

        author.save()
        return redirect("/social_distribution")
    
    return render(request, 'changeprofile.html', {'message': 'Form requirements failed, change failed.'})

@login_required
@api_view(['POST'])
def addentry(request):
    author = Author.objects.get(pk=request.user.username)

    # add additional data before serialization
    mutable_request_data = request.data.copy()
    mutable_request_data['belonging_url'] = author.url
    serializer = EntrySerializer(data=mutable_request_data)

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
    serializer = EntrySerializer(entries, many=True)
    return Response(serializer.data)

@login_required
@api_view(['POST'])
def deleteentry(request, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id, belonging_url=request.user.username)
    entry.is_deleted = True
    entry.save()
    return redirect("/social_distribution")

@login_required
@api_view(['POST'])
def editentry(request, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id, belonging_url=request.user.username)
    new_text = request.data.get('entry_text', '').strip()
    if new_text:
        entry.entry_text = new_text
        entry.save()
        return redirect("/social_distribution")
    return redirect("/social_distribution/editentry/" + str(entry_id))

@login_required
@api_view(['POST'])
def add_like(request):
    author = Author.objects.get(pk=request.user.username)
    liked_object = request.data.get('object', None)

    if not liked_object:
        return Response({"error": "Missing object field"}, status=400)

    like = Like.objects.create(author=author, object=liked_object)
    serializer = LikeSerializer(like)
    return Response(serializer.data)

@api_view(['GET'])
def get_likes(request, object_id):
    likes = Like.objects.filter(object=object_id).order_by('-published')
    serializer = LikeSerializer(likes, many=True)

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
def follow_requests(request):
    author = Author.objects.get(pk=request.user.username)

    requests = Follow.objects.filter(
        following =author,
        approved = False
    )

    return render(request, "follow_requests.html", {"requests": requests})

@login_required
def follow_author(request, username):
    current_author = Author.objects.get(pk=request.user.username)
    target_author = get_object_or_404(Author, pk=username)

    if current_author != target_author:
        Follow.objects.get_or_create(
            follower=current_author,
            following=target_author,
            defaults={"approved": False}
        )
    return redirect("profile", username=username)

@login_required
def approve_follow(request, username):
    current_author = Author.objects.get(pk=request.user.username)
    follower_author = get_object_or_404(Author, pk=username)

    follow = Follow.objects.get(
        follower=follower_author,
        following=current_author
    )

    follow.approved = True
    follow.save()

    return redirect("follow_request")

@login_required
def unfollow(request, username):
    current_author = Author.objects.get(pk=request.user.username)
    target_author = get_object_or_404(Author, pk=username)

    Follow.objects.filter(
        follower=current_author,
        following =target_author
    ).delete()

    return redirect("index")

@login_required
def author_list(request):
    current_author = Author.objects.get(pk=request.user.username)
    authors = Author.objects.exclude(url=current_author.url)
    return render(request, "social_distribution/author_list.html",{"authors": authors})

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

@api_view(['GET'])
def get_comments(request, entry_id):
    comments = Comment.objects.filter(entry__id=entry_id).order_by('-published')
    serializer = CommentSerializer(comments, many=True)

    return Response({
        "type": "comments",
        "id": f"/entries/{entry_id}/comments",
        "web": f"/entries/{entry_id}/comments",
        "page_number": 1,
        "size": len(serializer.data),
        "count": len(serializer.data),
        "src": serializer.data
    })

# POST a new comment
@login_required
@api_view(['POST'])
def post_entry_comment(request, entry_id):
    entry = get_object_or_404(TextEntry, id=entry_id)
    content = request.data.get("comment", "").strip()
    if not content:
        return Response({"error": "Missing comment content"}, status=400)

    comment = Comment.objects.create(
        author=request.user,
        entry=entry,
        content=content,
        content_type=request.data.get("contentType", "text/markdown"),
        created_at=timezone.now()
    )
    serializer = CommentSerializer(comment, context={'request': request})
    return Response(serializer.data, status=201)