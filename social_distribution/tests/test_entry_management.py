"""
Tests for entry management user stories:
- As an author, I want to edit my entries locally.
- As an author, I don't want anyone except the node admin to see my deleted entries.
- As an author, I want to delete my own entries locally.
- As an author, entries I create should always be visible to me until they are deleted.
- As a node admin, I want deleted entries to stay in the database and only be removed from the UI and API.
-As an author, entries I create can be images, so that I can share pictures and drawings.
"""

from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
import tempfile
import shutil

from social_distribution.models import TextEntry, Author

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

class DeleteEntryTests(TestCase):
    """
    As an author, I want to delete my own entries locally,
    so I can remove entries that are out of date or made by mistake.
    """

    def setUp(self):
        self.client = Client()
        self.user, self.author = make_user_and_author()
        self.client.login(username="testuser", password="testpass123")
        self.entry = make_entry(self.author)

    def test_author_can_soft_delete_own_entry(self):
        """POSTing to deleteentry marks is_deleted=True instead of removing the row."""
        url = reverse("social_distribution:deleteentry", args=[self.entry.pk])
        self.client.delete(url)

        self.entry.refresh_from_db()
        self.assertTrue(
            self.entry.is_deleted,
            "Entry should be soft-deleted (is_deleted=True), not removed from the DB.",
        )

    def test_delete_requires_login(self):
        """Unauthenticated users cannot delete entries."""
        self.client.logout()
        url = reverse("social_distribution:deleteentry", args=[self.entry.pk])
        self.client.delete(url)

        self.entry.refresh_from_db()
        self.assertFalse(self.entry.is_deleted)

    def test_author_cannot_delete_another_authors_entry(self):
        """An author cannot delete entries that belong to someone else."""
        _, other_author = make_user_and_author("otheruser", "otherpass123")
        other_entry = make_entry(other_author, text="Other's post")

        url = reverse("social_distribution:deleteentry", args=[other_entry.pk])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 404)
        other_entry.refresh_from_db()
        self.assertFalse(other_entry.is_deleted)

class DeletedEntryDatabaseTests(TestCase):
    """
    As a node admin, I want deleted entries to stay in the database
    and only be removed from the UI and API.
    """

    def setUp(self):
        self.client = Client()
        self.user, self.author = make_user_and_author()
        self.client.login(username="testuser", password="testpass123")
        self.entry = make_entry(self.author)

    def test_deleted_entry_row_persists_in_database(self):
        """After soft-delete, the database row still exists."""
        url = reverse("social_distribution:deleteentry", args=[self.entry.pk])
        self.client.post(url)

        exists = TextEntry.objects.filter(id=self.entry.pk).exists()
        self.assertTrue(exists, "Deleted entry must remain in the database.")

    def test_deleted_entry_accessible_for_admin(self):
        """Admins can still query deleted entries."""
        self.entry.is_deleted = True
        self.entry.save()

        all_entries = TextEntry.objects.filter(id=self.entry.pk)
        self.assertEqual(all_entries.count(), 1)
        entry = all_entries.first()
        assert entry is not None
        self.assertTrue(entry.is_deleted)

class EditEntryTests(TestCase):
    """
    As an author, I want to edit my entries locally, so that I'm not stuck 
    with a typo on a popular entry. Authors must not have to delete and
    re-create an entry to change the content.
    """

    def setUp(self):
        self.client = Client()
        self.user, self.author = make_user_and_author()
        self.client.login(username="testuser", password="testpass123")
        self.entry = make_entry(self.author, text="Original text")

    def test_author_can_edit_own_entry(self):
        """A valid POST with new text updates the entry in-place."""
        url = reverse("social_distribution:editentry", args=[self.entry.pk])
        self.client.post(url, {"entry_text": "Updated text"})

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.entry_text, "Updated text")

    def test_edit_preserves_entry_id(self):
        """Editing must update the existing row, not create a new one."""
        original_id = self.entry.pk
        url = reverse("social_distribution:editentry", args=[self.entry.pk])
        self.client.post(url, {"entry_text": "Changed"})

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.pk, original_id)

    def test_edit_requires_login(self):
        """Unauthenticated users cannot edit entries."""
        self.client.logout()
        url = reverse("social_distribution:editentry", args=[self.entry.pk])
        self.client.post(url, {"entry_text": "Hacked"})

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.entry_text, "Original text")

    def test_author_cannot_edit_another_authors_entry(self):
        """An author cannot edit entries that belong to someone else."""
        _, other_author = make_user_and_author("otheruser", "otherpass123")
        other_entry = make_entry(other_author, text="Other's original")

        url = reverse("social_distribution:editentry", args=[other_entry.pk])
        response = self.client.post(url, {"entry_text": "Tampered"})

        self.assertEqual(response.status_code, 404)
        other_entry.refresh_from_db()
        self.assertEqual(other_entry.entry_text, "Other's original")

    def test_empty_edit_does_not_overwrite(self):
        """Submitting blank text should not overwrite the entry."""
        url = reverse("social_distribution:editentry", args=[self.entry.pk])
        self.client.post(url, {"entry_text": "   "})

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.entry_text, "Original text")

    def test_author_can_change_visibility_when_editing(self):
        """Editing an existing entry can update visibility."""
        url = reverse("social_distribution:editentry", args=[self.entry.pk])
        self.client.post(url, {"entry_text": "Original text", "visibility": "FRIENDS"})

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.visibility, "FRIENDS")

class EntryVisibilityTests(TestCase):
    """
    As an author, I don't want anyone except the node admin to see my deleted entries.
    As an author, entries I create should always be visible to me until they are deleted.
    """

    def setUp(self):
        self.client = Client()
        self.user, self.author = make_user_and_author()
        self.client.login(username="testuser", password="testpass123")

    def test_public_entry_visible_to_author(self):
        entry = make_entry(self.author, visibility="PUBLIC")
        response = self.client.get(reverse("social_distribution:index"))
        self.assertIn(entry.pk, get_entry_ids(response))

    def test_friends_only_entry_visible_to_author(self):
        entry = make_entry(self.author, visibility="FRIENDS")
        response = self.client.get(reverse("social_distribution:index"))
        self.assertIn(entry.pk, get_entry_ids(response))

    def test_unlisted_entry_visible_to_author(self):
        entry = make_entry(self.author, visibility="UNLISTED")
        response = self.client.get(reverse("social_distribution:index"))
        self.assertIn(entry.pk, get_entry_ids(response))

    def test_entry_visible_before_delete_hidden_after(self):
        """Entry appears in stream before deletion and disappears after."""
        entry = make_entry(self.author, text="Visible until deleted")

        response = self.client.get(reverse("social_distribution:index"))
        self.assertIn(entry.pk, get_entry_ids(response))

        self.client.post(reverse("social_distribution:deleteentry", args=[entry.pk]))

        response = self.client.get(reverse("social_distribution:index"))
        self.assertNotIn(entry.pk, get_entry_ids(response))

    def test_deleted_entry_hidden_from_own_stream(self):
        entry = make_entry(self.author, is_deleted=True)
        response = self.client.get(reverse("social_distribution:index"))
        self.assertNotIn(entry.pk, get_entry_ids(response))

    def test_deleted_entry_hidden_from_public_profile(self):
        entry = make_entry(self.author, is_deleted=True)
        url = reverse("social_distribution:profile", args=[self.author.url])
        response = self.client.get(url)
        self.assertNotIn(entry.pk, get_entry_ids(response))

    def test_deleted_entry_hidden_from_other_users_stream(self):
        """A deleted entry from one author does not appear in another author's stream."""
        deleted_entry = make_entry(self.author, is_deleted=True)

        _, _ = make_user_and_author("visitor", "visitorpass")
        self.client.login(username="visitor", password="visitorpass")

        response = self.client.get(reverse("social_distribution:index"))
        self.assertNotIn(deleted_entry.pk, get_entry_ids(response))

    def test_deleted_entry_excluded_from_api(self):
        """The get_entries API endpoint does not return deleted entries."""
        deleted_entry = make_entry(self.author, is_deleted=True)

        response = self.client.get(reverse("social_distribution:get_entries"))
        self.assertEqual(response.status_code, 200)
        returned_ids = [e["id"] for e in response.json()]
        self.assertNotIn(deleted_entry.pk, returned_ids)

