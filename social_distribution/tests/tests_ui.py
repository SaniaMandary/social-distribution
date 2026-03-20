from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from social_distribution.models import Author
from django.contrib.auth.models import User
from social_distribution.utils import validate_create_author

# Create your tests here.
# https://docs.djangoproject.com/en/6.0/topics/testing/overview/
# https://docs.djangoproject.com/en/6.0/topics/testing/tools/

def make_user_and_author(username="testuser", password="testpass123"):
    """Create a Django auth user plus a matching Author record."""
    user = User.objects.create_user(username=username, password=password)

    validate_create_author(username, "localhost")
    
    author = Author.objects.get(username=username)

    return user, author

class LoginTest(TestCase):
    def setUp(self):
        self.c = Client()
        pass

    def test_login_redirect(self):
        # test redirect
        response = self.c.post("/social_distribution/", follow=True)
        self.assertTemplateUsed(response, "login.html")
        self.assertEqual(response.status_code, 200)

        response = self.c.post("/social_distribution/newentry", follow=True)
        self.assertTemplateUsed(response, "login.html")
        self.assertEqual(response.status_code, 200)

        response = self.c.post("/social_distribution/changeprofile", follow=True)
        self.assertTemplateUsed(response, "login.html")
        self.assertEqual(response.status_code, 200)

    def test_login(self):
        # test that we created new user, test log in
        user = "test123"
        password = "12345"

        response = self.c.post("/social_distribution/api/loginregister/", {"username" : user, "password" : password}, follow=True)
        self.assertTrue(self.c.login(username=user, password=password))

        self.c.logout()
        pass
    
    def test_incorrect_login(self):
        # test that we created new user, incorrect login
        user = "test123"
        password_wrong = "123"
        password = "1234567"

        # creates user
        response = self.c.post("/social_distribution/api/loginregister/", {"username" : user, "password" : password}, follow=True)
        self.c.logout()

        # use wrong password
        response = self.c.post("/social_distribution/api/loginregister/", {"username" : user, "password" : password_wrong}, follow=True)
        self.assertEqual(response.context['message'], 'Invalid username or password')
        pass

class ChangeProfileTest(TestCase):
    def setUp(self):
        self.c = Client()

        self.user = "test123"
        self.password = "12345"

        self.user, self.author =make_user_and_author(username=self.user, password=self.password)

        self.assertTrue(self.c.login(username=self.user, password=self.password))
        pass

    def test_change_profile_access(self):
        response = self.c.post("/social_distribution/changeprofile/", follow=True)
        self.assertTemplateUsed(response, "changeprofile.html")

    def test_change_profile_context_state(self):
        response = self.c.post("/social_distribution/changeprofile/", follow=True)
        self.assertEqual(response.context['name'], self.author.name)
        self.assertEqual(response.context['description'], '')
        self.assertEqual(response.context['picture'], '')
        self.assertEqual(response.context['github'], '')

    def test_change_profile(self):
        # test that the authors state has changed through API
        new_data = {
            'name': 'yaya',
            'description': 'cool',
            'picture': '???.png',
            'github': 'github?'
        }
        response = self.c.post("/social_distribution/api/editprofile/", data=new_data, follow=True, content_type='application/json')

        author = Author.objects.get(name=new_data['name'])
        self.assertEqual(author.name, new_data["name"])
        self.assertEqual(author.description, new_data["description"])
        self.assertEqual(author.picture, new_data["picture"])
        self.assertEqual(author.github, new_data["github"])

        # test the context state changes
        response = self.c.post("/social_distribution/changeprofile/", follow=True)
        self.assertEqual(response.context['name'], new_data['name'])
        self.assertEqual(response.context['description'], new_data['description'])
        self.assertEqual(response.context['picture'], new_data['picture'])
        self.assertEqual(response.context['github'], new_data['github'])

class IndexProfileTest(TestCase):
    def setUp(self):
        self.c = Client()

        self.user = "test123"
        self.password = "12345"

        self.user, self.author =make_user_and_author(username=self.user, password=self.password)

        self.assertTrue(self.c.login(username=self.user, password=self.password))
        pass

    def test_index_access(self):
        response = self.c.post("/social_distribution/", follow=True)
        self.assertTemplateUsed(response, "social_distribution/index.html")

    def test_index_entries_empty(self):
        response = self.c.post("/social_distribution/", follow=True)
        self.assertEqual(len(response.context['latest_entry_list']), 0)
    
    def test_add_entry_shows_on_index(self):
        response = self.c.post("/social_distribution/api/addentry/", data={
            'content':'this is a test'
        }, follow=True)
        
        response = self.c.post("/social_distribution/", follow=True) 
        self.assertEqual(len(response.context['latest_entry_list']), 1)
        self.assertEqual(response.context['latest_entry_list'][0].content, 'this is a test')
