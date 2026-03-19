from django import forms
from .models import TextEntry

class ChangeProfileForm(forms.Form):
    name = forms.CharField(label="name")
    description = forms.CharField(label="description", required=False)
    picture = forms.CharField(label="picture", required=False)
    github = forms.CharField(label="github", required=False)


class TextEntryForm(forms.ModelForm):
    image = forms.FileField(required=False)

    class Meta: 
        model = TextEntry
        fields = ['title', 'description','content', 'content_type', 'visibility'] 
        widgets = {
            'title': forms.Textarea(attrs={'rows': 1}),
            'description':forms.Textarea(attrs={'rows': 2}), 
            'content': forms.Textarea(attrs={'rows': 5}),
            'content_type': forms.Select(),
            'visibility': forms.Select(),
        }