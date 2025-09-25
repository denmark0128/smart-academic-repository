from django import forms
from .models import Paper
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, Div
from django.forms import ClearableFileInput


class PaperForm(forms.ModelForm):
    authors = forms.CharField(
        label='Authors',
        help_text='Separate full names with a newline. Example: Juan Dela Cruz\nMaria Lopez',
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
        widgets = {
            'file': ClearableFileInput(attrs={
                'class': 'custom-file-input',
                'id': 'file-upload',
                'accept': '.pdf,.docx',
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_id = 'upload-form'
        self.helper.form_class = 'space-y-4'  # vertical spacing

        self.helper.layout = Layout(
            # File field full width
            Field('file', css_class="file-input file-input-bordered w-full", id="file-upload"),

            # Title + Year side by side
            Div(
                Field('title', css_class="textarea textarea-bordered w-full"),
                Field('year', css_class="input input-bordered w-32"),
                css_class="grid grid-cols-3 gap-4"
            ),

            # Abstract (full width)
            Field('abstract', css_class="textarea textarea-bordered w-full"),

            # College + Program side by side
            Div(
                Field('college', css_class="input input-bordered w-full"),
                Field('program', css_class="input input-bordered w-full"),
                css_class="grid grid-cols-2 gap-4"
            ),

            # Authors field (textarea style)
            Field('authors', css_class="textarea textarea-bordered w-full"),

            # Submit button styled with DaisyUI
            Submit('submit', 'Upload Paper', css_class="btn btn-primary w-full")
        )

    def clean_authors(self):
        raw = self.cleaned_data['authors']
        lines = raw.strip().splitlines()
        names = [line.strip() for line in lines if line.strip()]
        if not names:
            raise forms.ValidationError("Please enter at least one author.")
        return names
