from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from social_distribution.models import Author, Comment, Like, TextEntry
from django.contrib.auth.models import User


def make_user_and_author(username="testuser", password="testpass123"):
    """Create a Django auth user plus a matching Author record."""
    user = User.objects.create_user(username=username, password=password)
    author = Author.objects.create(
        url=username,
        name=username,
        description="",
        picture="",
        github="",
    )
    return user, author

def make_entry(author, text="Hello world", visibility="PUBLIC", is_deleted=False):
    """Create and return a TextEntry owned by author."""
    return TextEntry.objects.create(
        belonging_url=author.url,
        entry_text=text,
        visibility=visibility,
        is_deleted=is_deleted,
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
        response = self.client.post(f"/social_distribution/api/likes/add/{self.entry.pk}/", follow=True)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("liked"))
        # Verify the like was created with full URL format
        liked_object = f"http://testserver/social_distribution/entries/{self.entry.pk}"
        like = Like.objects.filter(object=liked_object, author=self.author).first()
        self.assertIsNotNone(like)

    def test_get_likes_for_entry(self):
        # First, add a like to the entry with correct URL format
        liked_object = f"http://testserver/social_distribution/entries/{self.entry.pk}"
        Like.objects.create(object=liked_object, author=self.author)
        # Verify the like exists in the database
        likes = Like.objects.filter(object=liked_object)
        self.assertEqual(likes.count(), 1)
        self.assertEqual(likes[0].author, self.author)

    def test_unlike_entry(self):
        # Add a like to the entry
        liked_object = f"http://testserver/social_distribution/entries/{self.entry.pk}"
        like = Like.objects.create(object=liked_object, author=self.author)
        self.assertTrue(Like.objects.filter(id=like.pk).exists())

        # Now unlike it by posting to the same endpoint again (toggles)
        response = self.client.post(f"/social_distribution/api/likes/add/{self.entry.pk}/", follow=True)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertFalse(data.get("liked"))  # Should be unliked now
        
        # Assert that the like was removed
        self.assertFalse(Like.objects.filter(id=like.pk).exists()) 