from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views import generic
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required

from .models import Like, TextEntry, Author
from .forms import ChangeProfileForm
from .serializers import EntrySerializer, LikeSerializer

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
    # add required data to render posts
    entries = TextEntry.objects.filter(belonging_url=username, is_deleted=False, visibility='PUBLIC').order_by("-pub_date")

    entries_dictionary = {
        'latest_entry_list' : entries.values(),
        'author' : author.name,
        'picture_url' : author.picture
        }

    # render the page
    return render(request, "social_distribution/publicprofile.html", entries_dictionary)

class DetailView(generic.DetailView):
    model = TextEntry
    context_object_name = "entry"
    template_name = "social_distribution/detail.html"

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
    entries = TextEntry.objects.all()
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