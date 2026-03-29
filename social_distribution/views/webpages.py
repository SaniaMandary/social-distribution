import markdown
import logging
from itertools import chain
 
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views import generic
from django.db.models import Q
from django.contrib.auth.decorators import login_required
 
from ..models import Like, TextEntry, Author, Follow, Comment, Node
from ..forms import TextEntryForm, ChangeProfileForm
from ..utils import (
    NOT_DELETED, get_current_author, get_source_entry_url, friends,
    fetch_github_entries, render_markdown_entries, send_entry_to_followers,
    remote_node_get, remote_node_get_authors, remote_node_get_entries,
    upsert_remote_author, get_author_by_serial, remote_node_get_is_following,
    get_node_for_author, get_all_followers
)
from .api.entries import build_entry_image_url
 
logger = logging.getLogger(__name__)


# Web-UI Views 
def index(request):
    if not request.user.is_authenticated: # authenticated personal page view
        return redirect('/social_distribution/login')
    
    nodes = Node.objects.filter(is_enabled=True)

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
        if entry.pk: 
            entry.url = reverse("social_distribution:detail", kwargs={"pk": entry.pk})
        else: 
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
    try:
        author = get_object_or_404(Author, username=username, is_local=True)
    except Author.DoesNotExist:
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

    all_followers = get_all_followers(current_author)

    return render(request, "social_distribution/followers_list.html", {"followers": all_followers, "author": current_author})

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
    following = Follow.objects.filter(
        follower=current_author, approved=True
    )
    following_ids = following.values_list('following_id', flat=True)

    remote_friends = []
    for follow in following:
        if not follow.following.is_local:
            node = get_node_for_author(follow.following)
            isFollowing = remote_node_get_is_following(node, current_author, follow.following, auth_required=True)
            if isFollowing:
                remote_friends.append(follow.following)
    
    # of those, who also follows current_author back
    local_friends = Author.objects.filter(id__in=following_ids).filter(
        following__following=current_author,
        following__approved=True
        ).distinct()
    
    all_friends = list(local_friends) + remote_friends

    return render(request, "social_distribution/friends_list.html", {"friends_list": all_friends})
