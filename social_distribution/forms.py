from django import forms
from .models import TextEntry

class ChangeProfileForm(forms.Form):
    name = forms.CharField(label="name")
    description = forms.CharField(label="description")
    picture = forms.CharField(label="picture")
    github = forms.CharField(label="github")

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data


class TextEntryForm(forms.ModelForm):
    class Meta: 
        model = TextEntry
        fields = ['entry_text', 'content_type', 'visibility'] 
        widgets = {
            'entry_text': forms.Textarea(attrs={'rows': 5}),
            'content_type': forms.Select(),
            'visibility': forms.Select(),
            }
            