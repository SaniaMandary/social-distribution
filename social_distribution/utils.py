import base64 
import logging
import uuid
from urllib.parse import urlsplit
from django.http import HttpResponse
import requests as http_requests
from django.utils import timezone
from django.db.models import Q
from django.urls import reverse
from datetime import datetime, timezone as dt_tz
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime
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
            web=f"{node_host}/social_distribution/authors/{username}",
            name=username,
        )

        

def friends(author1, author2):
    isFriends = (
        Follow.objects.filter(follower=author1, following=author2, approved=True).exists()
        and
        Follow.objects.filter(follower=author2, following=author1, approved=True).exists()
    )

    # does author1 have a remote friend author2?
    if not isFriends:
        node = get_node_for_author(author2)
        if node:
            isFriends = Follow.objects.filter(follower=author1, following=author2, approved=True).exists() and remote_node_get_is_following(node, author1, author2, auth_required=True)
    
    # does author2 have a remote friend author1?
    if not isFriends:
        node = get_node_for_author(author1)
        if node:
            isFriends = Follow.objects.filter(follower=author2, following=author1, approved=True).exists() and remote_node_get_is_following(node, author2, author1, auth_required=True)

    return isFriends



def fetch_remote_author(author_data):
    # Get or create a remote author from an incoming API object.
    # Used by inbox to handle remote authors.
    return upsert_remote_author(author_data)


def _normalize_remote_host(author_id, host=''):
    if host:
        return host.rstrip('/') + '/'

    marker = '/api/authors/'
    if marker in author_id:
        base = author_id.split(marker, 1)[0]
        return f"{base}/api/"

    parsed = urlsplit(author_id)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/"

    return ''


def upsert_remote_author(author_data):
    author_id = (author_data or {}).get('id')
    if not author_id:
        return None

    display_name = (author_data.get('displayName') or '').strip()
    fallback_username = author_id.rstrip('/').split('/')[-1]

    # Seed the serial from the full FQID — globally unique, so no cross-node collisions.
    serial = uuid.uuid5(uuid.NAMESPACE_URL, author_id)

    defaults = {
        'serial': serial,
        'username': display_name or fallback_username,
        'host': _normalize_remote_host(author_id, author_data.get('host', '')),
        'web': author_data.get('web', ''),
        'is_local': False,
        'is_approved': True,
        'name': display_name or fallback_username,
        'description': 'remote author',
        'picture': author_data.get('profileImage', ''),
        'github': author_data.get('github', ''),
    }
    author, _ = Author.objects.update_or_create(id=author_id, defaults=defaults)
    return author


def get_or_create_remote_author_from_fqid(author_fqid):
    if not author_fqid:
        return None
    return upsert_remote_author({
        'id': author_fqid,
        'displayName': author_fqid.rstrip('/').split('/')[-1],
    })



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

    if entry.remote_fqid:
        web = entry.remote_fqid.replace('/api/authors/', '/authors/')
    elif entry.author.web:
        web = f"{entry.author.web.rstrip('/')}/entries/{entry.pk}"
    else:
        web = entry.fqid

    return {
        "type": "comments",
        "id": f"{entry.fqid}/comments",
        "web": web,
        "page_number": 1,
        "size": page_size,
        "count": total,
        "src": CommentSerializer(first_page, many=True, context=context).data,
    }


#Github fetch logic 


def fetch_github_entries(author, cooldown):
    """
    Fetch new GitHub public events for author and save them as PUBLIC entries.

    Returns a list of the newly created TextEntry objects (saved, with PKs).
    Returns an empty list if nothing new was fetched or the cooldown blocked the call.
    """
    if not author.github:
        return []

    if cooldown: 
        if author.github_last_polled:
            elapsed = timezone.now() - author.github_last_polled
            if elapsed.total_seconds() < 900:
                return []

    github_username = author.github.rstrip('/').split('/')[-1]
    if not github_username:
        return []

    try:
        response = http_requests.get(
            f"https://api.github.com/users/{github_username}/events/public",
            timeout=5,
            headers={"Accept": "application/vnd.github+json"}
        )
        if response.status_code != 200:
            logger.warning(f"GitHub API returned {response.status_code} for {github_username}")
            return []
        events = response.json()
    except Exception as e:
        logger.error(f"GitHub fetch failed: {e}")
        return []

    last_polled = author.github_last_polled
    
    existing_times = set(
        TextEntry.objects.filter(
            author=author, source_type='github'
        ).values_list('published', flat=True)
    )

    new_entries = []

    for event in events:
        try:
            event_time = datetime.strptime(
                event.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=dt_tz.utc)
        except Exception:
            continue

        # Skip anything at or before last_polled
        if last_polled and event_time <= last_polled:
            continue

        # Skip if an entry with this exact timestamp already exists
        if event_time in existing_times:
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

    saved = []
    for entry in new_entries:
        entry.save()
        saved.append(entry)

    # Always update last_polled, even if no new entries, so the cooldown works
    # correctly regardless of whether bulk_create produced anything.
    author.github_last_polled = timezone.now()
    author.save(update_fields=['github_last_polled'])

    return saved

# make a get request to a node with optional auth, used for fetching remote data from other nodes.
def remote_node_get(node, endpoint: str, auth_required=True):
    if not node.is_enabled:
        logger.warning(f"Attempted to GET from disabled node {node.url}")
        return None

    url = node.url.rstrip('/') + '/' + endpoint.lstrip('/')
    try:
        if auth_required:
            return http_requests.get(url, auth=(node.outgoing_username, node.outgoing_password), timeout=5)
        else:
            return http_requests.get(url, timeout=5)
    except Exception as e:
        logger.error(f"Failed to GET from {url}: {e}")
        return None

# get a list of remote authors from a node
# returns: list of Author objects
def remote_node_get_authors(node, auth_required=True):
    response = remote_node_get(node, "api/authors/", auth_required=auth_required)
    if response is None or response.status_code != 200:
        return []

    body = response.json()
    authors = body.get('authors', body.get('src', []))
    authors_actual = []
    for i in range(len(authors)):
        author = convert_remote_author_to_local(authors[i])
        if author is not None:
            authors_actual.append(author)
    return authors_actual

# get a list of remote entries for a given author from a node
# returns: list of TextEntry objects
def remote_node_get_entries(node, author, auth_required=True):
    author_key = author.id.rstrip('/').split('/')[-1]
    response = remote_node_get(node, f"api/authors/{author_key}/entries/", auth_required=auth_required)
    if response is None or response.status_code != 200:
        return []
    entries = response.json().get('src', []) 
    entries_actual = []
    for i in range(len(entries)):
        entry = convert_remote_entry_to_local(entries[i], author)
        if entry is not None:
            entries_actual.append(entry)
    return entries_actual

def remote_node_get_is_following(node, author, target_author, auth_required=True):
    author_key = author.id.rstrip('/').split('/')[-1]
    target_author_key = target_author.id.rstrip('/').split('/')[-1]
    response = remote_node_get(node, f"api/authors/{target_author_key}/following/{author.fqid}", auth_required=auth_required)
    
    if response.status_code == 200:
        return True
    elif response.status_code == 404:
        return False
    else:
        print(f"Unexpected response checking following status: {response.status_code}")
        return False
    pass

def remote_node_get_followers(current_author, auth_required=True):
    remote_followers = []
    for node in Node.objects.filter(is_enabled=True):
        for author in remote_node_get_authors(node, auth_required=auth_required):
            if remote_node_get_is_following(node, current_author, author, auth_required=auth_required):
                remote_followers.append(Follow(following=current_author, follower=author, approved=auth_required))
    return remote_followers

def convert_remote_author_to_local(author_data):
    # Convert incoming author data from a remote node into a local Author object.
    return upsert_remote_author(author_data)

def convert_remote_entry_to_local(entry_data, author):
    """Convert incoming entry data from a remote node into a saved TextEntry object.
    """
    entry_id = entry_data.get('id', '')
    if not entry_id:
        return None

    raw_published = entry_data.get('published')
    if raw_published:
        try:
            published = parse_datetime(raw_published) or timezone.now()
        except Exception:
            published = timezone.now()
    else:
        published = timezone.now()

    visibility = entry_data.get('visibility', 'PUBLIC')
    if visibility == 'DELETED':
        return None

    entry, _ = TextEntry.objects.update_or_create(
        remote_fqid=entry_id,
        defaults={
            'author': author,
            'title': entry_data.get('title', ''),
            'description': entry_data.get('description', ''),
            'content': entry_data.get('content', ''),
            'content_type': entry_data.get('contentType', 'text/plain'),
            'source_type': 'remote',
            'visibility': visibility,
            'published': published,
        }
    )
    return entry

def get_source_entry_url(entry):
    """
    Returns the frontend URL for linking to an entry in the UI.
    For remote entries, derives the URL from the remote FQID by replacing the API path.
    For local entries, returns the local detail view URL.
    """
    if entry.remote_fqid:
        # Convert API FQID to frontend web URL:
        # http://node/api/authors/{serial}/entries/{id} -> http://node/authors/{serial}/entries/{id}
        return entry.remote_fqid.replace('/api/authors/', '/authors/')
    return reverse("social_distribution:detail", kwargs={"pk": entry.pk})

# get all followers including remote ones, assumes remote is the ground truth for follow status
def get_all_followers(for_author):
    remote_followers = remote_node_get_followers(for_author, auth_required=True)

    followers = Follow.objects.filter(
        following=for_author,
        approved=True
    ).select_related('follower')

    return list(followers) + remote_followers

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
        follows = get_all_followers(author)
        recipients = [f.follower for f in follows]
    elif entry.visibility == 'FRIENDS':
        # ssnd only to friends (mutual follows)
        follows = get_all_followers(author)
        recipients = [f.follower for f in follows if friends(author, f.follower)]
    elif entry.visibility == 'DELETED':
        # send delete notification to all followers
        follows = get_all_followers(author)
        recipients = [f.follower for f in follows]
    else:
        return

    for recipient in recipients:
        if not recipient.is_local:
            print("SENDING TO", recipient.name)
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
    follows = get_all_followers(author)
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
    follows = get_all_followers(author)
    for f in follows:
        if not f.follower.is_local:
            send_to_inbox(f.follower, serialized)

