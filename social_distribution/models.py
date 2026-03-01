from datetime import datetime
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
    pub_date = models.DateTimeField("date published", default=datetime.now)   # Store the published date in a datetime field in the database
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
    timestamp = models.DateTimeField(auto_now_add=True)