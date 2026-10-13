from django import forms
from django.core.validators import RegexValidator

class ContactForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        required=True,
        validators=[
            RegexValidator(
                regex='^[a-zA-Z\s]*$',
                message='Name should contain only alphabets and spaces.',
                code='invalid_name'
            )
        ],
        widget=forms.TextInput(attrs={
            'placeholder': 'Your Name',
            'class': 'form-control',
            'style': 'height: 50px; font-size: 16px;'
        })
    )

    # Email field
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'placeholder': 'Your Email',
            'class': 'form-control',
            'style': 'height: 50px; font-size: 16px;'
        })
    )

    # Subject field
    subject = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Subject',
            'class': 'form-control',
            'style': 'height: 50px; font-size: 16px;'
        })
    )

    # Message field with minimum length validation
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Your Message',
            'class': 'form-control',
            'style': 'font-size: 16px;',
            'rows': 6 
        }),
        required=True,
        min_length=10,
        error_messages={
            'min_length': 'Message must be at least 10 characters long.'
        }
    )

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Name cannot be empty or contain only whitespace.')
        if len(name) < 2:
            raise forms.ValidationError('Name must be at least 2 characters long.')
        if name.lower() == 'admin':
            raise forms.ValidationError('Name cannot be "Admin".')
        return name

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError('Email address cannot be empty or whitespace.')
        return email

    def clean_subject(self):
        subject = self.cleaned_data.get('subject', '').strip()
        if not subject:
            raise forms.ValidationError('Subject cannot be empty or contain only whitespace.')
        if len(subject) < 3:
            raise forms.ValidationError('Subject must be at least 3 characters long.')
        return subject

    def clean_message(self):
        message = self.cleaned_data.get('message', '').strip()
        if not message:
            raise forms.ValidationError('Message cannot be empty or contain only whitespace.')
        if len(message) < 10:
            raise forms.ValidationError('Message must be at least 10 characters long.')

        forbidden_words = ['spam', 'advertisement']
        for word in forbidden_words:
            if word in message.lower():
                raise forms.ValidationError(f'Message contains forbidden word: {word}.')
        return message

    def clean(self):
        return super().clean()
