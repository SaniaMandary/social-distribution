from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
 
from ..models import Author, Follow
from ..utils import get_current_author, send_follow_to_inbox
 


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
