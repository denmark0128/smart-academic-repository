from django import forms
from .models import Paper
from django.forms import ClearableFileInput
from django.contrib.auth.forms import AuthenticationForm
# We no longer need crispy_forms
# from crispy_forms.helper import FormHelper
# from crispy_forms.layout import Submit, Layout, Field, Div

# --- Base styling for all widgets ---
# We can define the styles here to reuse them, just like your example
WIDGET_CLASSES = "w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2 dark:bg-zinc-800 dark:text-zinc-300"
SELECT_CLASSES = f"{WIDGET_CLASSES} select" # For <select> elements
TEXTAREA_CLASSES = f"{WIDGET_CLASSES} textarea" # For <textarea>
FILE_INPUT_CLASSES = f"{WIDGET_CLASSES} file-input" # For <input type="file">


class StyledLoginForm(AuthenticationForm):
    """
    Login form styled to match the rest of the application.
    """
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": WIDGET_CLASSES,
            "placeholder": "Username",
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": WIDGET_CLASSES,
            "placeholder": "Password",
        })
    )

class PaperForm(forms.ModelForm):
    """
    Form for uploading a new Paper, styled with simple Tailwind classes
    instead of crispy_forms.
    """
    
    # --- Field Overrides ---
    # We define the fields here to customize labels, help text, and widgets
    
    file = forms.FileField(
        label="Upload Paper File",
        help_text="Accepted formats: .pdf, .docx, .chm",
        widget=ClearableFileInput(attrs={
            'class': FILE_INPUT_CLASSES,
            'id': 'file-upload',
            'accept': '.pdf,.docx,.chm',
        })
    )
    
    title = forms.CharField(
        label='Paper Title',
        widget=forms.Textarea(attrs={
            'class': TEXTAREA_CLASSES,
            'rows': 3,
            'placeholder': "Your research paper title here"
        })
    )
    
    abstract = forms.CharField(
        label='Abstract',
        widget=forms.Textarea(attrs={
            'class': TEXTAREA_CLASSES,
            'rows': 5,
            'placeholder': "Brief summary of your research paper, include purpose and methods used"
        }),
        required=False
    )
    
    year = forms.IntegerField(
        label='Year Published',
        required=False,
        widget=forms.TextInput(attrs={
            'class': WIDGET_CLASSES,
            'placeholder': 'YYYY',
            'maxlength': '4',
            # Basic client-side validation to only allow numbers
            'oninput': "this.value = this.value.replace(/[^0-9]/g, '').slice(0, 4)",
        })
    )

    authors = forms.CharField(
        label='Authors',
        help_text='Separate full names with a comma (,)',
        widget=forms.Textarea(attrs={
            'class': TEXTAREA_CLASSES,
            'placeholder': "Dela Cruz, Juan A., Lopez, Maria B., Reyes, Pedro C.",
            'rows': 3
        })
    )

    # --- Meta Class ---
    # This connects the form to the model and defines the base widgets
    # for fields we *didn't* override above (like college and program).
    class Meta:
        model = Paper
        fields = ['file', 'title', 'abstract', 'college', 'program', 'year', 'authors']
        
        # Apply default styling to any fields not explicitly defined above
        widgets = {
            'college': forms.Select(attrs={'class': SELECT_CLASSES}),
            'program': forms.Select(attrs={'class': SELECT_CLASSES}),
        }

    # We no longer need __init__ because we are not using FormHelper
    # def __init__(self, *args, **kwargs): 
    #     super().__init__(*args, **kwargs)
    #     self.helper = FormHelper()
    #     ... (all crispy_forms logic removed) ...

    def clean_authors(self):
        raw = self.cleaned_data['authors']
        lines = raw.strip().splitlines()
        names = [line.strip() for line in lines if line.strip()]
        if not names:
            raise forms.ValidationError("Please enter at least one author.")
        return names
