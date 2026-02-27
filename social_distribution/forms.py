from django import forms

class ChangeProfileForm(forms.Form):
    name = forms.CharField(label="name")
    description = forms.CharField(label="description")
    picture = forms.CharField(label="picture")
    github = forms.CharField(label="github")

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data