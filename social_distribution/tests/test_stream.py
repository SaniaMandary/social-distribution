"""
Tests for stream user stories:
- As an author, I want a "stream" which shows all the entries I should know about, so I don't have to switch between different pages.
- As an author, I want my stream page to show me all the public entries my node knows about, so I can find new people to follow.
- As an author, I want my stream page to show me all the unlisted and friends-only entries of all the authors I follow.
- As an author, I want my stream page to show me the most recent version of an entry if it has been edited.
- As an author, I want my stream page to not show me entries that have been deleted.

via Entries Public API
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from social_distribution.models import TextEntry, Author, Follow
from social_distribution.utils import validate_create_author
import uuid

def make_user_and_author(username="testuser", password="testpass123"):
    """Create a Django auth user plus a matching Author record."""
    user = User.objects.create_user(username=username, password=password)

    validate_create_author(username, "localhost")
    
    author = Author.objects.get(username=username)

    return user, author

def make_entry(author, text="Hello world", visibility="PUBLIC", is_deleted=False):
    """Create and return a TextEntry owned by author."""
    if is_deleted:
        visibility = "DELETED"

    return TextEntry.objects.create(
        author=author,
        content=text,
        visibility=visibility,
    )
# tests api for empty/no entries visibility
class TestEmptyStreamVisibility(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1, self.author1 = make_user_and_author()
        self.client.login(username="testuser", password="testpass123")
        
    def test_api_author_entry_detail(self):
        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,1])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        url = reverse("social_distribution:api_author_entry_detail", args=[uuid.uuid4(),1])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_api_entry_fqid(self):
        url = reverse("social_distribution:api_entry_fqid", args=[1])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_api_author_entries(self):
        url = reverse("social_distribution:api_author_entries", args=[self.author1.serial])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

# tests api for visibility as the author of the posts
class TestSelfStreamVisibility(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1, self.author1 = make_user_and_author()
        self.client.login(username="testuser", password="testpass123")

        self.e1 = make_entry(self.author1, text="public test entry", visibility="PUBLIC")
        self.e2 = make_entry(self.author1, text="unlisted test entry", visibility="UNLISTED")
        self.e3 = make_entry(self.author1, text="friends test entry", visibility="FRIENDS")
        self.e4 = make_entry(self.author1, text="friends test entry", visibility="PUBLIC", is_deleted=True)

    def test_api_author_entry_detail(self):
        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e1.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], "public test entry")

        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e2.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], "unlisted test entry")

        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e3.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], "friends test entry")

        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e4.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 404)

        url = reverse("social_distribution:api_author_entry_detail", args=[uuid.uuid4(),self.e1.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 404)

    def test_api_entry_fqid(self):
        url = reverse("social_distribution:api_entry_fqid", args=[self.e1.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], 'public test entry')

        url = reverse("social_distribution:api_entry_fqid", args=[self.e2.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], 'unlisted test entry')

        url = reverse("social_distribution:api_entry_fqid", args=[self.e3.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], 'friends test entry')

        url = reverse("social_distribution:api_entry_fqid", args=[self.e4.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 404)

    def test_api_author_entries(self):
        url = reverse("social_distribution:api_author_entries", args=[self.author1.serial])
        response = self.client.get(url)
        self.assertEqual(len(response.json()), 3) # got 3 entries back?
        self.assertEqual(response.status_code, 200)

# tests api for visibility as a non-signed in user
class TestAnonymousStreamVisibility(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1, self.author1 = make_user_and_author()
        self.client.login(username="testuser", password="testpass123")

        self.e1 = make_entry(self.author1, text="public test entry", visibility="PUBLIC")
        self.e2 = make_entry(self.author1, text="unlisted test entry", visibility="UNLISTED")
        self.e3 = make_entry(self.author1, text="friends test entry", visibility="FRIENDS")
        self.e4 = make_entry(self.author1, text="friends test entry", visibility="PUBLIC", is_deleted=True)

        self.client.logout()

    def test_api_author_entry_detail(self):
        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e1.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], "public test entry")

        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e2.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], "unlisted test entry")

        # friends posts are hidden
        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e3.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 403)

        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e4.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 404)

    def test_api_entry_fqid(self):
        url = reverse("social_distribution:api_entry_fqid", args=[self.e1.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], 'public test entry')

        url = reverse("social_distribution:api_entry_fqid", args=[self.e2.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], 'unlisted test entry')

        url = reverse("social_distribution:api_entry_fqid", args=[self.e3.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 403)

        url = reverse("social_distribution:api_entry_fqid", args=[self.e4.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 404)

    def test_api_author_entries(self):
        url = reverse("social_distribution:api_author_entries", args=[self.author1.serial])
        response = self.client.get(url)
        self.assertEqual(len(response.json()), 1) # got only public entries back?
        self.assertEqual(response.status_code, 200)

# tests api for visibility as a follower of another user that posts stuff
class TestFollowerStreamVisibility(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1, self.author1 = make_user_and_author()
        self.client.login(username="testuser", password="testpass123")

        self.e1 = make_entry(self.author1, text="public test entry", visibility="PUBLIC")
        self.e2 = make_entry(self.author1, text="unlisted test entry", visibility="UNLISTED")
        self.e3 = make_entry(self.author1, text="friends test entry", visibility="FRIENDS")
        self.e4 = make_entry(self.author1, text="friends test entry", visibility="PUBLIC", is_deleted=True)

        self.client.logout()

        self.user2, self.author2 = make_user_and_author("testuser2")
        self.client.login(username="testuser2", password="testpass123")

        Follow.objects.create(follower=self.author2, following=self.author1, approved=True)

    def test_api_author_entry_detail(self):
        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e1.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], "public test entry")

        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e2.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], "unlisted test entry")

        # friends posts are hidden
        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e3.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 403)

        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial,self.e4.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 404)

    def test_api_entry_fqid(self):
        url = reverse("social_distribution:api_entry_fqid", args=[self.e1.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], 'public test entry')

        url = reverse("social_distribution:api_entry_fqid", args=[self.e2.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], 'unlisted test entry')

        url = reverse("social_distribution:api_entry_fqid", args=[self.e3.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200) # only need to be authenticated to access friend post via this api

        url = reverse("social_distribution:api_entry_fqid", args=[self.e4.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 404)

    def test_api_author_entries(self):
        url = reverse("social_distribution:api_author_entries", args=[self.author1.serial])
        response = self.client.get(url)
        self.assertEqual(len(response.json()), 2) # got only public+unlisted entries back?
        self.assertEqual(response.status_code, 200)
        
# tests api for visibility as a friend of another user that posts stuff
class TestFriendsStreamVisibility(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1, self.author1 = make_user_and_author()
        self.client.login(username="testuser", password="testpass123")

        self.e1 = make_entry(self.author1, text="public test entry", visibility="PUBLIC")
        self.e2 = make_entry(self.author1, text="unlisted test entry", visibility="UNLISTED")
        self.e3 = make_entry(self.author1, text="friends test entry", visibility="FRIENDS")
        self.e4 = make_entry(self.author1, text="friends test entry", visibility="PUBLIC", is_deleted=True)

        self.client.logout()

        self.user2, self.author2 = make_user_and_author("testuser2")
        self.client.login(username="testuser2", password="testpass123")

        Follow.objects.create(follower=self.author2, following=self.author1, approved=True)
        Follow.objects.create(follower=self.author1, following=self.author2, approved=True)

    def test_api_author_entry_detail(self):
        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial, self.e1.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], "public test entry")

        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial, self.e2.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], "unlisted test entry")

        # friends posts are accessible
        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial, self.e3.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)

        url = reverse("social_distribution:api_author_entry_detail", args=[self.author1.serial, self.e4.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 404)

    def test_api_entry_fqid(self):
        url = reverse("social_distribution:api_entry_fqid", args=[self.e1.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], 'public test entry')

        url = reverse("social_distribution:api_entry_fqid", args=[self.e2.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['content'], 'unlisted test entry')

        url = reverse("social_distribution:api_entry_fqid", args=[self.e3.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 200) 

        url = reverse("social_distribution:api_entry_fqid", args=[self.e4.pk])
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 404)

    def test_api_author_entries(self):
        url = reverse("social_distribution:api_author_entries", args=[self.author1.serial])
        response = self.client.get(url)
        self.assertEqual(len(response.json()), 3) # got only public+unlisted+friends entries back?
        self.assertEqual(response.status_code, 200)