from datetime import datetime
from django.db import models

# Create your models here.

class TextEntry(models.Model):
    entry_text = models.CharField(max_length=300)    # Store the text in a char field in the database
    pub_date = models.DateTimeField("date published", default=datetime.now)   # Store the published date in a datetime field in the database
