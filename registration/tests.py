from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from registration.views import validate_password


class PasswordValidationTestCase(TestCase):
    def test_password_too_short(self):
        valid, msg = validate_password("Short1!")
        self.assertFalse(valid)
        self.assertIn("at least 8 characters", msg)

    def test_password_missing_uppercase(self):
        valid, msg = validate_password("lowercase1!")
        self.assertFalse(valid)
        self.assertIn("uppercase", msg)

    def test_password_missing_lowercase(self):
        valid, msg = validate_password("UPPERCASE1!")
        self.assertFalse(valid)
        self.assertIn("lowercase", msg)

    def test_password_missing_number(self):
        valid, msg = validate_password("NoNumberHere!")
        self.assertFalse(valid)
        self.assertIn("number", msg)

    def test_password_missing_special_char(self):
        valid, msg = validate_password("NoSpecial123")
        self.assertFalse(valid)
        self.assertIn("special character", msg)

    def test_password_contains_spaces(self):
        valid, msg = validate_password("Pass word123!")
        self.assertFalse(valid)
        self.assertIn("spaces", msg)

    def test_valid_strong_password(self):
        valid, msg = validate_password("SecurePass123!")
        self.assertTrue(valid)
        self.assertEqual(msg, "")


class LoginPageValidationTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser@example.com",
            email="testuser@example.com",
            password="StrongPassword123!"
        )

    def test_login_empty_fields(self):
        response = self.client.post(reverse('login'), {'email': '', 'password': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn('errors', response.context)
        self.assertIn('email', response.context['errors'])
        self.assertIn('password', response.context['errors'])

    def test_login_invalid_email_format(self):
        response = self.client.post(reverse('login'), {'email': 'not-an-email', 'password': 'SomePassword123!'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('errors', response.context)
        self.assertIn('email', response.context['errors'])

    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('login'), {'email': 'testuser@example.com', 'password': 'WrongPassword123!'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('errors', response.context)
        self.assertIn('non_field', response.context['errors'])

    def test_login_successful(self):
        response = self.client.post(reverse('login'), {'email': 'testuser@example.com', 'password': 'StrongPassword123!'})
        self.assertRedirects(response, reverse('home'))


class SignupPageValidationTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.existing_user = User.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            password="Password123!"
        )

    def test_signup_empty_submission(self):
        response = self.client.post(reverse('signup'), {})
        self.assertEqual(response.status_code, 200)
        self.assertIn('errors', response.context)
        errors = response.context['errors']
        self.assertIn('username', errors)
        self.assertIn('first_name', errors)
        self.assertIn('last_name', errors)
        self.assertIn('email', errors)
        self.assertIn('password', errors)
        self.assertIn('confirm_password', errors)
        self.assertIn('terms', errors)

    def test_signup_invalid_username_characters(self):
        response = self.client.post(reverse('signup'), {
            'username': 'user!@#',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'newuser@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
            'terms': 'true'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('username', response.context['errors'])

    def test_signup_duplicate_username(self):
        response = self.client.post(reverse('signup'), {
            'username': 'existinguser',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'brandnew@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
            'terms': 'true'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('username', response.context['errors'])
        self.assertIn('already exists', response.context['errors']['username'])

    def test_signup_duplicate_email(self):
        response = self.client.post(reverse('signup'), {
            'username': 'brandnewuser',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'existing@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
            'terms': 'true'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('email', response.context['errors'])
        self.assertIn('already exists', response.context['errors']['email'])

    def test_signup_password_mismatch(self):
        response = self.client.post(reverse('signup'), {
            'username': 'brandnewuser',
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'brandnew@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'DifferentPassword123!',
            'terms': 'true'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('confirm_password', response.context['errors'])
        self.assertIn('do not match', response.context['errors']['confirm_password'])

    def test_signup_invalid_name(self):
        response = self.client.post(reverse('signup'), {
            'username': 'brandnewuser',
            'first_name': 'John123',
            'last_name': 'Doe!',
            'email': 'brandnew@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
            'terms': 'true'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('first_name', response.context['errors'])
        self.assertIn('last_name', response.context['errors'])


class ForgotPasswordValidationTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="registered@example.com",
            password="Password123!"
        )

    def test_forgot_password_empty_email(self):
        response = self.client.post(reverse('forgot_password'), {'email': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn('errors', response.context)
        self.assertIn('email', response.context['errors'])

    def test_forgot_password_invalid_email(self):
        response = self.client.post(reverse('forgot_password'), {'email': 'invalid-email'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('errors', response.context)
        self.assertIn('email', response.context['errors'])

    def test_forgot_password_non_existent_email(self):
        response = self.client.post(reverse('forgot_password'), {'email': 'unknown@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('errors', response.context)
        self.assertIn('No account found', response.context['errors']['email'])


class ResetPasswordValidationTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="resettester",
            email="resettester@example.com",
            password="OldPassword123!"
        )

    def test_reset_password_unverified_session_redirects(self):
        response = self.client.get(reverse('reset_password'))
        self.assertRedirects(response, reverse('forgot_password'))

    def test_reset_password_weak_password(self):
        session = self.client.session
        session['reset_email'] = 'resettester@example.com'
        session['reset_verified'] = True
        session.save()

        response = self.client.post(reverse('reset_password'), {
            'new_password': 'weak',
            'confirm_password': 'weak'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('errors', response.context)
        self.assertIn('new_password', response.context['errors'])

    def test_reset_password_mismatch(self):
        session = self.client.session
        session['reset_email'] = 'resettester@example.com'
        session['reset_verified'] = True
        session.save()

        response = self.client.post(reverse('reset_password'), {
            'new_password': 'StrongNewPass123!',
            'confirm_password': 'DifferentPass123!'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('errors', response.context)
        self.assertIn('confirm_password', response.context['errors'])
