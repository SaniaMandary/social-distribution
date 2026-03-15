from django import forms
from .models import TextEntry

class ChangeProfileForm(forms.Form):
    name = forms.CharField(label="name")
    description = forms.CharField(label="description", required=False)
    picture = forms.CharField(label="picture", required=False)
    github = forms.CharField(label="github", required=False)


class TextEntryForm(forms.ModelForm):
    class Meta: 
        model = TextEntry
        fields = ['entry_text', 'content_type', 'visibility'] 
        widgets = {
            'entry_text': forms.Textarea(attrs={'rows': 5}),
            'content_type': forms.Select(),
            'visibility': forms.Select(),
        }