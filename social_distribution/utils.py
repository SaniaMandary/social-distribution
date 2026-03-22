import base64 
import logging
import uuid
from django.http import HttpResponse
import requests as http_requests
from django.utils import timezone
from django.db.models import Q
from django.urls import reverse
from datetime import datetime, timezone as dt_tz
from rest_framework.response import Response
from .models import (
    Node, Like, Comment, TextEntry, Author, Follow,
)

logger = logging.getLogger(__name__)
NOT_DELETED = ~Q(visibility='DELETED')

# all remote endpoints need http basic auth. 

def is_authenticated_request(request):
    if request.user.is_authenticated:
        return True
    if authenticate_remote_node(request):
        return True
    return False


# Author helper methods 

def get_author_by_serial(username):
    return Author.objects.get(username=username)


def get_current_author(request):
    return Author.objects.get(username=request.user.username)


def author_exists(username):
    return Author.objects.filter(username=username).exists()


def validate_create_author(username, node_host):
    if not Author.objects.filter(username=username).exists():
        author_uuid = uuid.uuid4()
        Author.objects.create(
            id=f"{node_host}/social_distribution/api/authors/{author_uuid}",
            serial=author_uuid,
            username=username,
            host=f"{node_host}/social_distribution/api/",
            name=username,
        )

        

def friends(author1, author2):
    return (
        Follow.objects.filter(follower=author1, following=author2, approved=True).exists()
        and
        Follow.objects.filter(follower=author2, following=author1, approved=True).exists()
    )


def fetch_remote_author(author_data):
    # Get or create a remote author from an incoming API object.
    # Used by inbox to handle remote authors.
    author_id = author_data.get('id')
    if not author_id:
        return None

    author, _ = Author.objects.get_or_create(
        id=author_id,
        defaults={
            'serial': uuid.uuid4,
            'username': '',
            'host': author_data.get('host', ''),
            'name': author_data.get('displayName', ''),
            'picture': author_data.get('profileImage', ''),
            'github': author_data.get('github', ''),
            'is_local': False,
        }
    )
    return author



# Visibility helper methods 
def can_view_entry(request, entry):
    # Check if the request user can view this entry.
    if entry.is_deleted:
        return False
    if entry.visibility in ('PUBLIC', 'UNLISTED'):
        return True
    if entry.visibility == 'FRIENDS':
        if not request.user.is_authenticated:
            return False
        viewer = get_current_author(request)
        return viewer == entry.author or friends(viewer, entry.author)
    return False


def render_markdown_entries(entries):
    import markdown as md
    for entry in entries or []:
        if entry.content_type == 'text/markdown':
            entry.content_rendered = md.markdown(entry.content)
            entry.header_rendered = md.markdown(entry.title)


# page pagination 

def get_page_args(request, default_size=10):
    page = int(request.query_params.get('page', 1))
    size = int(request.query_params.get('size', default_size))
    return page, size


def paginate_set(queryset, page, size):
    start = (page - 1) * size
    end = start + size
    return queryset[start:end]


def build_paginated_response(type_name, items_key, serialized_data, page_number, page_size, total_count):
    return {
        "type": type_name,
        "page_number": page_number,
        "size": page_size,
        "count": total_count,
        items_key: serialized_data,
    }


# Object builders 

def build_likes_object(object_fqid, web_url, context, page_size=50):
    from .serializers import LikeSerializer
    likes = Like.objects.filter(object_url=object_fqid).order_by('-published')
    total = likes.count()
    first_page = likes[:page_size]
    return {
        "type": "likes",
        "id": f"{object_fqid}/likes",
        "web": web_url,
        "page_number": 1,
        "size": page_size,
        "count": total,
        "src": LikeSerializer(first_page, many=True, context=context).data,
    }


def build_comments_object(entry, context, page_size=5):
    from .serializers import CommentSerializer
    comments = Comment.objects.filter(local_entry=entry).order_by('-published')
    total = comments.count()
    first_page = comments[:page_size]
    return {
        "type": "comments",
        "id": f"{entry.fqid}/comments",
        "web": f"{entry.author.host}/authors/{entry.author.serial}/entries/{entry.pk}",
        "page_number": 1,
        "size": page_size,
        "count": total,
        "src": CommentSerializer(first_page, many=True, context=context).data,
    }


#Github fetch logic 


def fetch_github_entries(author, cooldown):
    if not author.github:
        return

    if cooldown: 
        if author.github_last_polled:
            elapsed = timezone.now() - author.github_last_polled
            if elapsed.total_seconds() < 900:
                return


    github_username = author.github.rstrip('/').split('/')[-1]
    if not github_username:
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
    except Exception as e:
        logger.error(f"GitHub fetch failed: {e}")
        return

    last_polled = author.github_last_polled
    new_entries = []

    for event in events:
        try:
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
            description = f"Starred [{repo_name}](https://github.com/{repo_name})"
            
        elif event_type == "ForkEvent":
            forkee = payload.get("forkee", {}).get("full_name", "")
            description = f"Forked [{repo_name}](https://github.com/{repo_name}) to [{forkee}](https://github.com/{forkee})"
        else:
            continue
        
        new_entries.append(TextEntry(
            author=author,
            title=f"GitHub: {event_type}",
            content=description,
            content_type='text/markdown',
            visibility='PUBLIC',
            published=event_time,
            source_type='github',
        ))

    if new_entries:
        TextEntry.objects.bulk_create(new_entries)

    author.github_last_polled = timezone.now()
    author.save(update_fields=['github_last_polled'])

# make a get request to a node with optional auth, used for fetching remote data from other nodes.
def remote_node_get(node, endpoint: str, auth_required=True):
    if not node.is_enabled:
        response = HttpResponse(
            "Node is disabled", 
            status=503, 
            reason="Node is disabled"
        )
        response.reason = "Node is disabled"
        return response

    url = node.url.rstrip('/') + '/' + endpoint.lstrip('/')
    if auth_required:
        return http_requests.get(url, auth=(node.outgoing_username, node.outgoing_password), timeout=5)
    else:
        return http_requests.get(url, timeout=5)

# get a list of remote authors from a node
# returns: list of Author objects
def remote_node_get_authors(node, auth_required=True):
    response = remote_node_get(node, "api/authors/", auth_required=auth_required)
    authors = response.json().get('authors', []) 
    authors_actual = []
    for i in range(len(authors)):
        author = convert_remote_author_to_local(authors[i])
        authors_actual.append(author)
    return authors_actual

# get a list of remote entries for a given author from a node
# returns: list of TextEntry objects
def remote_node_get_entries(node, author, auth_required=True):
    response = remote_node_get(node, f"api/authors/{author.serial}/entries/", auth_required=auth_required)
    entries = response.json().get('src', []) 
    entries_actual = []
    for i in range(len(entries)):
        entry = convert_remote_entry_to_local(entries[i], author)
        entries_actual.append(entry)
    return entries_actual

def convert_remote_author_to_local(author_data):
    # Convert incoming author data from a remote node into a local Author object.
    serial = author_data.get('id').split("/")[-1]
    return Author(
        id=author_data.get('id'),
        serial=serial,
        username=author_data.get('displayName', ''),

        host=author_data.get('host', ''),
        is_local=False,
        is_approved=True,  # Assume remote authors are approved by default
        name=author_data.get('displayName', ''),
        description="remote author",
        picture=author_data.get('profileImage', ''),
        github=author_data.get('github', ''),
    )

def convert_remote_entry_to_local(entry_data, author):
    # Convert incoming entry data from a remote node into a local TextEntry object.
    from .serializers import EntrySerializer
    r_entry = EntrySerializer(data=entry_data)
    if r_entry.is_valid():
        r_entry = TextEntry(**r_entry.validated_data) # https://stackoverflow.com/questions/37232436/django-rest-serializer-create-object-without-saving
        r_entry.source_type = 'remote'
        r_entry.remote_fqid = entry_data.get('id', '')
        r_entry.author = author
        return r_entry
    else:
        print("Invalid entry data:", r_entry.errors)
        return None

    return TextEntry(
        author=author,
        remote_fqid=entry_data.get('id', ''),
        title=entry_data.get('title', ''),
        description=entry_data.get('description', ''),
        content=entry_data.get('content', ''),
        image=entry_data.get('image', ''),
        published=entry_data.get('published', timezone.now()),

        content_type=entry_data.get('contentType', 'text/markdown'),
        source_type=entry_data.get('sourceType', 'remote'),
        visibility=entry_data.get('visibility', 'PUBLIC'),
    )

def get_source_entry_url(entry):
    if entry.source_type == 'remote':
        # replace https://herokuapp.com/social_distribution/api/authors/uuid/entries/1
        # with https://herokuapp.com/social_distribution/entries/1
        # this may be a source of incompatibility if other groups use fqid purely

        return entry.remote_fqid.replace(f"api/authors/{entry.author.serial}/entries/", "")
    else:
        return reverse("social_distribution:detail", kwargs={"pk": entry.pk})


def authenticate_remote_node(request):
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Basic '):
        return None

    try:
        decoded = base64.b64decode(auth_header[6:]).decode('utf-8')
        username, password = decoded.split(':', 1)
    except Exception:
        return None

    try:
        node = Node.objects.get( # Look up a node whose credentials match what was sent to us.
            incoming_username=username,  
            incoming_password=password,
            is_enabled=True,
        )
        return node
    except Node.DoesNotExist:
        return None


def remote_node_post(node, endpoint, data):
    if not node.is_enabled:
        logger.warning(f"Attempted to POST to disabled node {node.url}")
        return None

    url = node.url.rstrip('/') + '/' + endpoint.lstrip('/')
    try:
        response = http_requests.post(
            url,
            json=data,
            auth=(node.outgoing_username, node.outgoing_password),
            timeout=10,
        )
        logger.info(f"POST {url} -> {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Failed to POST to {url}: {e}")
        return None


def get_node_for_author(author):
    if author.is_local:
        return None

    author_host = author.host.rstrip('/')

    for node in Node.objects.filter(is_enabled=True):
        node_url = node.url.rstrip('/')
        # Match if the author's host starts with or equals the node URL
        if author_host.startswith(node_url) or node_url.startswith(author_host):
            return node

    logger.warning(f"No matching node found for remote author {author.id} (host={author.host})")
    return None

#build the inbox API endpoint path for a given author 
def get_inbox_endpoint(author):
    fqid = author.id
    marker = 'api/authors/'
    idx = fqid.find(marker)
    if idx != -1:
        real_serial = fqid[idx + len(marker):].strip('/')
        return f"api/authors/{real_serial}/inbox/"

    return f"api/authors/{author.serial}/inbox/"


# send payload to a single authors inbox if they are remote handle by finding their node and POST. 
# local delivery is handled elsehwere.  
def send_to_inbox(target_author, data):
    if target_author.is_local:
        return  # local authors don't need inbox delivery

    node = get_node_for_author(target_author)
    if not node:
        logger.warning(f"Cannot send to inbox of {target_author.id}: no matching node")
        return

    endpoint = get_inbox_endpoint(target_author)
    remote_node_post(node, endpoint, data)


# after creating/editing/deleteing an entry push it all to remote followers/friends inboxes 
def send_entry_to_followers(entry, request):
    from .serializers import EntrySerializer

    author = entry.author
    if not author.is_local:
        return  # only push entries created on OUR node

    serialized = EntrySerializer(entry, context={'request': request}).data

    # Determine who should receive this entry
    if entry.visibility in ('PUBLIC', 'UNLISTED'):
        # send to all followers
        follows = Follow.objects.filter(following=author, approved=True).select_related('follower')
        recipients = [f.follower for f in follows]
    elif entry.visibility == 'FRIENDS':
        # ssnd only to friends (mutual follows)
        follows = Follow.objects.filter(following=author, approved=True).select_related('follower')
        recipients = [f.follower for f in follows if friends(author, f.follower)]
    elif entry.visibility == 'DELETED':
        # send delete notification to all followers
        follows = Follow.objects.filter(following=author, approved=True).select_related('follower')
        recipients = [f.follower for f in follows]
    else:
        return

    for recipient in recipients:
        if not recipient.is_local:
            send_to_inbox(recipient, serialized)


# local author follows a remote author post the follow request to remote authors inbox
def send_follow_to_inbox(follow_obj, request):
    from .serializers import FollowSerializer

    target = follow_obj.following
    if target.is_local:
        return  # local follow, no remote push needed

    serialized = FollowSerializer(follow_obj, context={'request': request}).data
    send_to_inbox(target, serialized)



# When a local author likes something, PSOT the like to the entry/comment author's inbox 
# if they are a remote author 
def send_like_to_inbox(like, target_author, request):
    from .serializers import LikeSerializer

    if target_author.is_local:
        return

    serialized = LikeSerializer(like, context={'request': request}).data
    send_to_inbox(target_author, serialized)



#When a local author comments on an entry, POST the comment to the entry authors
# inbox if they are a remote author. 
def send_comment_to_inbox(comment, target_author, request):
    from .serializers import CommentSerializer

    if target_author.is_local:
        return

    serialized = CommentSerializer(comment, context={'request': request}).data
    send_to_inbox(target_author, serialized)


def send_like_to_followers(like, entry, request):
    """
    Push a like to all remote followers of the entry's author,
    so they can see it when viewing the entry.
    """
    from .serializers import LikeSerializer

    author = entry.author
    if not author.is_local:
        return

    serialized = LikeSerializer(like, context={'request': request}).data
    follows = Follow.objects.filter(following=author, approved=True).select_related('follower')
    for f in follows:
        if not f.follower.is_local:
            send_to_inbox(f.follower, serialized)


def send_comment_to_followers(comment, entry, request):
    """
    Push a comment to all remote followers of the entry's author,
    so they can see it when viewing the entry.
    """
    from .serializers import CommentSerializer

    author = entry.author
    if not author.is_local:
        return

    serialized = CommentSerializer(comment, context={'request': request}).data
    follows = Follow.objects.filter(following=author, approved=True).select_related('follower')
    for f in follows:
        if not f.follower.is_local:
            send_to_inbox(f.follower, serialized)
