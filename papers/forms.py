from django import forms
from .models import Paper
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, Div
from django.forms import ClearableFileInput
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import RegexValidator

class StyledLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "input input-bordered w-full dark:bg-zinc-800 dark:border-zinc-700",
            "placeholder": "Username",
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "input input-bordered w-full dark:bg-zinc-800 dark:border-zinc-700",
            "placeholder": "Password",
        })
    )

class PaperForm(forms.ModelForm):
    file = forms.FileField(
        label="Upload Paper File",
        help_text="Accepted formats: PDF, DOCX, CHM\nIf your file follows the standard layout, metadata will be extracted automatically.",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "border border-gray-300 rounded-lg p-3 w-full cursor-pointer hover:border-blue-400 focus:ring-2 focus:ring-blue-500",
                "id": "file-upload", 
            }
        ),
    )

    class Meta:
        model = Paper  # replace with your actual model name
        fields = "__all__"

    authors = forms.CharField(
        label='Authors',
        help_text='Separate full names with a comma (,)',
        widget=forms.Textarea(attrs={
            'placeholder': "Dela Cruz , Juan A., Lopez, Maria B.,Reyes, Pedro C.",
            'rows': 3
        })
    )
    title = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': "Your research paper title here"
        })
    )
    year = forms.IntegerField(
        required=False,  # allow blank
        widget=forms.TextInput(attrs={
            'placeholder': 'YYYY',
            'oninput': 'this.value = this.value.slice(0,4)',  # limit typing
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
                'accept': '.pdf,.docx,.chm',
            })
        }

    def __init__(self, *args, **kwargs): 
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_id = 'upload-form'
        self.helper.label_class = "block text-sm font-semibold text-gray-700 dark:text-zinc-300"
        self.helper.form_class = 'space-y-6'

        self.helper.layout = Layout(
            Div(
                # 🔹 LEFT COLUMN (File Upload)
                Div(
                    Field(
                        'file',
                        css_class="file-input file-input-bordered w-full dark:text-zinc-300 dark:bg-zinc-800 dark:border-zinc-700",
                        id="file-upload"
                    ),
                    css_class="w-full sm:w-1/3"
                ),

                # 🔹 RIGHT COLUMN (Other fields)
                Div(
                    # Title + Year side by side
                    Div(
                        Field(
                            'title',
                            css_class="textarea textarea-bordered w-full sm:col-span-1.5. dark:text-zinc-300 dark:bg-zinc-800 dark:border-zinc-700"
                        ),
                        Field(
                            'year',
                            css_class="input input-bordered w-full sm:col-span-0.5 dark:text-zinc-300 dark:bg-zinc-800 dark:border-zinc-700"
                        ),
                        css_class="grid grid-cols-1 sm:grid-cols-2 gap-4"
                    ),

                    # Abstract full width
                    Field('abstract', css_class="textarea textarea-bordered w-full dark:text-zinc-300 dark:bg-zinc-800 dark:border-zinc-700"),

                    # College + Program
                    Div(
                        Field('college', css_class="select select-bordered w-full dark:text-zinc-300 dark:bg-zinc-800 dark:border-zinc-700"),
                        Field('program', css_class="select select-bordered w-full dark:text-zinc-300 dark:bg-zinc-800 dark:border-zinc-700"),
                        css_class="grid grid-cols-1 sm:grid-cols-2 gap-4"
                    ),

                    # Authors
                    Field('authors', css_class="textarea textarea-bordered w-full dark:text-zinc-300 dark:bg-zinc-800 dark:border-zinc-700"),

                    # Submit button
                    Submit(
                        'submit',
                        'Upload Paper',
                        css_class="btn border border-gray-200 dark:border-zinc-700 px-2 dark:text-zinc-300 dark:bg-zinc-800 w-full sm:w-auto"
                    ),
                    css_class="space-y-4 w-full sm:w-2/3"
                ),

                css_class="flex flex-col sm:flex-row gap-6"
            )
        )

    def clean_authors(self):
        raw = self.cleaned_data['authors']
        lines = raw.strip().splitlines()
        names = [line.strip() for line in lines if line.strip()]
        if not names:
            raise forms.ValidationError("Please enter at least one author.")
        return names
