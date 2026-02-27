from django.contrib import admin

from .models import TextEntry, Author

# Register your models here.
admin.site.register(TextEntry)
admin.site.register(Author)