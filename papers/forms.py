from django import forms
from .models import Paper
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

class PaperForm(forms.ModelForm):
    authors = forms.CharField(
        label='Authors',
        help_text='Separate full names with a dot. Example: Juan Dela Cruz. Maria Lopez.',
        widget=forms.Textarea(attrs={
            'placeholder': "Juan Dela Cruz. Maria Lopez. Pedro Reyes",
            'rows': 2
        })
    )

    class Meta:
        model = Paper
        fields = ['title', 'abstract', 'year', 'authors', 'file']

    def __init__(self, *args, **kwargs):
        super(PaperForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit'))

    def clean_authors(self):
        raw = self.cleaned_data['authors']
        # Keep the dot at the end by splitting on '. ' (dot + space)
        names = [name.strip() + '.' for name in raw.split('. ') if name.strip()]
        
        # Remove trailing extra dot if user already added it
        names = [name if name.endswith('.') else name + '.' for name in names]

        if not names:
            raise forms.ValidationError("Please enter at least one author.")
        return names

