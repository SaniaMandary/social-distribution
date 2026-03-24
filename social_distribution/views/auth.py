import base64
 
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
 
from rest_framework.decorators import api_view
from rest_framework.response import Response
 
from ..models import TextEntry, Author
from ..forms import ChangeProfileForm
from ..serializers import EntrySerializer
from ..utils import (
    get_current_author, author_exists, validate_create_author,
    send_entry_to_followers,
)
from .api.entries import validate_entry_content_payload



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