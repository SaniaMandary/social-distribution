import base64 
import logging
import uuid
import requests as http_requests
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timezone as dt_tz
from .models import Like, Comment, TextEntry, Author, Follow

logger = logging.getLogger(__name__)
NOT_DELETED = ~Q(visibility='DELETED')


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
