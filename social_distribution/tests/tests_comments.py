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


class CommentTest(TestCase):
    def setUp(self):
        self.client = Client()  
        self.user, self.author = make_user_and_author()
        self.client.login(username=self.user.username, password="testpass123")
        self.entry = make_entry(self.author)

    def test_add_comment(self):
        comment_data = {
            'entry': self.entry.fqid,
            "comment": "This is a test comment",
            "contentType": "text/markdown"
        }
        
        url = reverse("social_distribution:api_author_commented", args=[self.author.serial])
        response = self.client.post(
            url,
            data=comment_data,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)

        # Verify the comment was created in the database
        comment = Comment.objects.filter(entry=self.entry.fqid, author=self.author).first()
        assert comment is not None
        self.assertEqual(comment.comment, comment_data["comment"])
        self.assertEqual(comment.content_type, comment_data["contentType"])

    def test_get_comments(self):
        # Create a comment to retrieve
        comment = Comment.objects.create(
            author=self.author, entry=self.entry.fqid, local_entry=self.entry,
            comment="This is a test comment", content_type="text/markdown"
        )

        url = reverse("social_distribution:api_entry_comments", args=[self.author.serial, self.entry.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data.get("type"), "comments")
        comments = data.get("src", [])  # Response uses 'src' not 'comments'
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["comment"], comment.comment)
        self.assertEqual(comments[0]["contentType"], comment.content_type)
        self.assertEqual(comments[0]["author"]["id"], self.author.id)
        self.assertEqual(comments[0]["author"]["displayName"], self.author.name)
        self.assertIn("published", comments[0])

    def test_like_comment(self):
        # Create a comment to like  
        comment = Comment.objects.create(
            author=self.author, entry=self.entry.fqid, local_entry=self.entry,
            comment="This is a test comment", content_type="text/markdown"
        )

        url = reverse("social_distribution:api_comment_likes", args=[self.author.serial, self.entry.pk, comment.fqid])
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data.get("type")=='like')
        self.assertTrue(data.get("id"))

        # Verify the like was created with correct URL format
        like_exists = Like.objects.filter(object_url=comment.fqid, author=self.author).exists()
        self.assertTrue(like_exists)    
    
