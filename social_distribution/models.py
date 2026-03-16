from django.utils import timezone
from django.db import models

class Author(models.Model):
    url = models.CharField(primary_key=True)
    host = models.CharField(max_length=500, blank=True, default='')
    is_local = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=200, blank=True, default='')
    picture = models.CharField(max_length=200, blank=True, default='')
    github = models.CharField(max_length=200, blank=True, default='')
    github_last_polled = models.DateTimeField(null=True, blank=True)

    @property
    def fqid(self):
        return f"{self.host}/social_distribution/api/authors/{self.url}"

class TextEntry(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('text/plain', 'Plain Text'),
        ('text/markdown', 'CommonMark'),
    ]

    SOURCE_TYPE = [
        ('native', 'Native'), 
        ('github', 'GitHub'), 
    ]

    VISIBILITY_CHOICES = [
        ('PUBLIC', 'Public'),
        ('FRIENDS', 'Friends'),
        ('UNLISTED', 'Unlisted'),
    ]

    belonging_url = models.CharField()
    entry_text = models.TextField()
    pub_date = models.DateTimeField("date published", default=timezone.now)
    is_deleted = models.BooleanField(default=False)
    content_type = models.CharField(
        max_length=50,
        choices=CONTENT_TYPE_CHOICES,
        default='text/plain'
    )

    source_type = models.CharField(
        max_length=20, 
        choices=SOURCE_CHOICES, 
        default='native'
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='PUBLIC'
    )

class Like(models.Model):
    object = models.CharField(max_length=200)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    published = models.DateTimeField(auto_now_add=True)

class Follow(models.Model):
    follower = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name="following"
    )
    following = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name="followers"
    )
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Comment(models.Model):
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    entry = models.ForeignKey(TextEntry, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField()
    content_type = models.CharField(max_length=100, default="text/markdown")
    created_at = models.DateTimeField(auto_now_add=True)
    # Not stored in DB
    likes_count: int = 0
    user_liked: bool = False