from django.contrib import admin
from .models import TextEntry, Author, Comment, Node

# Register your models here.
admin.site.register(TextEntry)
admin.site.register(Author)
admin.site.register(Comment)

@admin.register(Node)
class NodeAdmin(admin.ModelAdmin): 
    list_display = ('url', 'is_enabled', 'outgoing_username', 'incoming_username')
    list_filter = ('is_enabled',)