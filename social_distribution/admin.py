from django.contrib import admin

from .models import TextEntry, Author, Comment, Node

# Register your models here.
admin.site.register(TextEntry)
admin.site.register(Author)
admin.site.register(Comment)
admin.site.register(Node)