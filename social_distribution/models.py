from django.utils import timezone
from django.db import models

# Create your models here.
class Author(models.Model):
    url = models.CharField(primary_key=True)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=200)
    picture = models.CharField(max_length=200)
    github = models.CharField(max_length=200)

class TextEntry(models.Model):
    CONTENT_TYPE_CHOICES = {
        ('text/plain', 'PLain Text'),
        ('text/markdown', 'CommonMark'),
    }

    belonging_url = models.CharField()
    entry_text = models.CharField(max_length=300)    # Store the text in a char field in the database
    pub_date = models.DateTimeField("date published", default=timezone.now)   # Store the published date in a datetime field in the database
    is_deleted = models.BooleanField(default=False)  # soft delete flag
    visibility = models.CharField(max_length=20, default='PUBLIC')  # PUBLIC, FRIENDS, UNLISTED
    content_type = models.CharField(
        max_length=50,
        choices=CONTENT_TYPE_CHOICES,
        default='text/plain'
    )

class Like(models.Model):
    object = models.CharField(max_length=200) #could be an entry or comment
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

   

