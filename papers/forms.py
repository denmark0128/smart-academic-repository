from django import forms
from .models import Paper
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field
from crispy_forms.layout import Fieldset, Div

class PaperForm(forms.ModelForm):
    authors = forms.CharField(
        label='Authors',
        help_text='Separate full names with a dot. Example: Juan Dela Cruz. Maria Lopez.',
        widget=forms.Textarea(attrs={
            'placeholder': "Juan Dela Cruz\nMaria Lopez\nPedro Reyes",
            'rows': 3
        })
    )

    title = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': "Your research paper title here"
        })
    )
    abstract = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': "Brief summary of your research paper"
        }),
        required=False
    )

    class Meta:
        model = Paper
        fields = ['file', 'title', 'abstract', 'college', 'program', 'year', 'authors']

    def __init__(self, *args, **kwargs):
        super(PaperForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'

        # Custom layout: file at top, title as textarea
        self.helper.layout = Layout(
            Field('file'),  # ⬅ file input moved to top
            Field('title'),
            Field('abstract'),
            Field('college'),
            Field('program'),
            Field('year'),
            Field('authors'),
            Submit('submit', 'Submit')
        )

    def clean_authors(self):
        raw = self.cleaned_data['authors']
        lines = raw.strip().splitlines()
        names = [line.strip() for line in lines if line.strip()]
        if not names:
            raise forms.ValidationError("Please enter at least one author.")
        return names
