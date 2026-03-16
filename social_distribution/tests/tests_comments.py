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


class CommentTest(TestCase):
    def setUp(self):
        self.client = Client()  
        self.user, self.author = make_user_and_author()
        self.client.login(username=self.user.username, password="testpass123")
        self.entry = make_entry(self.author)

    def test_add_comment(self):
        comment_data = {
            "comment": "This is a test comment",
            "contentType": "text/markdown"
        }
        response = self.client.post(
            f"/social_distribution/api/entries/{self.entry.pk}/comments/add/",
            data=comment_data,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)

        # Verify the comment was created in the database
        comment = Comment.objects.filter(entry=self.entry, author=self.author).first()
        assert comment is not None
        self.assertEqual(comment.content, comment_data["comment"])
        self.assertEqual(comment.content_type, comment_data["contentType"])

    def test_get_comments(self):
        # Create a comment to retrieve
        comment = Comment.objects.create(
            author=self.author,
            entry=self.entry,
            content="This is a test comment",
            content_type="text/markdown"
        )

        response = self.client.get(f"/social_distribution/api/entries/{self.entry.pk}/comments/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("type"), "comments")
        comments = data.get("src", [])  # Response uses 'src' not 'comments'
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["content"], comment.content)
        self.assertEqual(comments[0]["content_type"], comment.content_type)
        self.assertEqual(comments[0]["author"]["url"], self.author.url)
        self.assertEqual(comments[0]["author"]["displayName"], self.author.name)
        self.assertIn("published", comments[0])

    def test_like_comment(self):
        # Create a comment to like
        comment = Comment.objects.create(
            author=self.author,
            entry=self.entry,
            content="This is a test comment",
            content_type="text/markdown"
        )

        response = self.client.post(f"/social_distribution/api/comments/{comment.pk}/likes/", follow=True)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("liked"))

        # Verify the like was created with correct URL format
        liked_object = f"http://testserver/social_distribution/comments/{comment.pk}"
        like_exists = Like.objects.filter(object=liked_object, author=self.author).exists()
        self.assertTrue(like_exists)    
    
