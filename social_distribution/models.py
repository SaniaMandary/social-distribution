import uuid 
from django.utils import timezone
from django.db import models

class Author(models.Model):
    #fqid (e.g. http://node/api/authors/111)
    id = models.URLField(primary_key=True, max_length=500)
    serial = models.UUIDField(default=uuid.uuid4, unique=True) 
    username = models.CharField(max_length=150, blank=True, default='') 

    host = models.URLField(max_length=500, blank=True, default='') 
    is_local = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=200, blank=True, default='')
    picture = models.CharField(max_length=200, blank=True, default='')
    github = models.CharField(max_length=200, blank=True, default='')
    github_last_polled = models.DateTimeField(null=True, blank=True)

    @property
    def fqid(self):
        return self.id


class TextEntry(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('text/plain', 'Plain Text'),
        ('text/markdown', 'CommonMark'),
        ('image/png', 'PNG Image'),
        ('image/jpeg', 'JPEG Image'),
        ('image/gif', 'GIF Image'),
    ]

    SOURCE_TYPE = [
        ('native', 'Native'), 
        ('github', 'GitHub'), 
    ]

    VISIBILITY_CHOICES = [
        ('PUBLIC', 'Public'),
        ('FRIENDS', 'Friends'),
        ('UNLISTED', 'Unlisted'),
        ('DELETED', 'Deleted'),
    ]
    # Should implement a primary key variable for any specific entry. 
    #belonging_url --> author
    # entry_header --> title 
    # entry_text --> content 
    # pub_date --> published 
    # is_deleted --> deleted (now conveyed through visibility field)

    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="entries")
    title = models.CharField(max_length=250, default='')
    description = models.CharField(max_length=500, blank=True, default='')
    content = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='entries/', blank=True, null=True)
    published = models.DateTimeField(default=timezone.now)
    
    content_type = models.CharField(
        max_length=50,
        choices=CONTENT_TYPE_CHOICES,
        default='text/plain'
    )

    source_type = models.CharField(
        max_length=10, 
        choices=SOURCE_TYPE, 
        default='native'
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='PUBLIC'
    )

    @property
    def fqid(self):
        return f"{self.author.fqid}/entries/{self.pk}"

    @property
    def is_deleted(self):
        return self.visibility == 'DELETED'



class Like(models.Model):
    #fqid of object being liked 
    object_url = models.URLField(max_length=500)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="likes")
    published = models.DateTimeField(auto_now_add=True)

    @property 
    def fqid(self):
        return f"{self.author.fqid}/liked/{self.pk}"


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
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="comments")
    entry = models.URLField(max_length=500)
    
    local_entry = models.ForeignKey(
        TextEntry, on_delete=models.CASCADE,
        related_name="comments_on",
        null=True, blank=True
    )
    comment = models.TextField()
    content_type = models.CharField(max_length=100, default="text/markdown")
    published = models.DateTimeField(auto_now_add=True)

    @property 
    def fqid(self):
        return f"{self.author.fqid}/commented/{self.pk}"