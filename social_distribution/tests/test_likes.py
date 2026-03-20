from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from social_distribution.models import Author, Comment, Like, TextEntry
from django.contrib.auth.models import User
from social_distribution.utils import validate_create_author
from django.urls import reverse

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

def get_entry_ids(response, context_key="latest_entry_list"):
    """Extract entry IDs from a response context list."""
    entries = list(response.context.get(context_key) or [])
    return [e.id for e in entries]

class LikeTest(TestCase):
    def setUp(self):
        self.client = Client()  
        self.user, self.author = make_user_and_author()
        self.client.login(username=self.user.username, password="testpass123")
        self.entry = make_entry(self.author)

    def test_add_like_to_entry(self):
        url = reverse("social_distribution:api_entry_likes", args=[self.author.serial, self.entry.pk])  
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data.get("type"), "like")

        # Verify the like was created with full URL format
        liked_object = f"localhost/social_distribution/api/authors/{self.author.serial}/entries/{self.entry.pk}"
        like = Like.objects.filter(object_url=liked_object, author=self.author).first()
        self.assertIsNotNone(like)

    def test_get_likes_for_entry(self):
        # First, add a like to the entry with correct URL format
        liked_object = self.entry.fqid 
        Like.objects.create(object_url=liked_object, author=self.author)
        # Verify the like exists in the database
        likes = Like.objects.filter(object_url=liked_object)
        self.assertEqual(likes.count(), 1)
        self.assertEqual(likes[0].author, self.author)

    def test_unlike_entry(self):
        # Add a like to the entry
        liked_object = self.entry.fqid 
        like = Like.objects.create(object_url=liked_object, author=self.author)
        self.assertTrue(Like.objects.filter(id=like.pk).exists())

        # Now unlike it by posting to the same endpoint again (toggles)
        url = reverse("social_distribution:api_entry_likes", args=[self.author.serial, self.entry.pk])  
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("success"), True)
        self.assertEqual(data.get("liked"), False)
        
        # Assert that the like was removed
        self.assertFalse(Like.objects.filter(id=like.pk).exists()) 