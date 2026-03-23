from django.test import TestCase, Client
from django.urls import reverse
from social_distribution.models import Author, Follow, TextEntry, Node
from django.contrib.auth.models import User
from social_distribution.views import friends
from social_distribution.utils import validate_create_author
from unittest.mock import patch

class FollowingAuthorsTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="user1", password="pass1")
        self.user2 = User.objects.create_user(username="user2", password="pass2")
        self.user3 = User.objects.create_user(username="user3", password="pass3")

        validate_create_author("user1", "localhost")
        validate_create_author("user2", "localhost")
        validate_create_author("user3", "localhost")

        self.author1 = Author.objects.get(username="user1")
        self.author2 = Author.objects.get(username="user2")
        self.author3 = Author.objects.get(username="user3")

        self.client = Client()

    def test_follow_request_approval(self):
        #user2 follows user1
        self.client.login(username='user2', password='pass2')
        response = self.client.post(reverse('social_distribution:follow_author', args=['user1']))
        self.assertEqual(response.status_code, 302)

        #check that follow request exists and not approved
        follow_request = Follow.objects.get(follower=self.author2, following=self.author1)
        self.assertFalse(follow_request.approved)

        #user1 approves follow request
        self.client.login(username='user1', password='pass1')
        self.client.get(reverse('social_distribution:approve_follow', args=[str(self.author2.serial)]))
        follow_request.refresh_from_db()
        self.assertTrue(follow_request.approved)

    def test_unfollow(self):
        #user2 follows user1
        Follow.objects.create(follower=self.author2, following=self.author1, approved=True)

        self.client.login(username='user2', password='pass2')
        response = self.client.post(reverse('social_distribution:unfollow', args=['user1']))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Follow.objects.filter(follower=self.author2, following=self.author1).exists())

    def test_friends(self):
        #not friends
        self.assertFalse(friends(self.author1, self.author2))

        #mutual follows
        Follow.objects.create(follower=self.author1, following=self.author2, approved=True)
        Follow.objects.create(follower=self.author2, following=self.author1, approved=True)
        self.assertTrue(friends(self.author1, self.author2))

    def test_friends_only_entries(self):
        #mutual follows
        Follow.objects.create(follower=self.author1, following=self.author2, approved=True)
        Follow.objects.create(follower=self.author2, following=self.author1, approved=True)

        #create friends only post
        TextEntry.objects.create(
            author=self.author1,
            content='Friends only post',
            visibility='FRIENDS'
        )

        #friend views profile
        self.client.login(username='user2', password='pass2')
        response = self.client.get(reverse('social_distribution:profile', args=['user1']))
        self.assertContains(response, 'Friends only post')

        #non friend views profile
        self.client.login(username='user3', password='pass3')
        response = self.client.get(reverse('social_distribution:profile', args=['user1']))
        self.assertNotContains(response, 'Friends only post')


class RemoteFollowingTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(username="localuser", password="pass1")
        validate_create_author("localuser", "http://testserver")
        self.local_author = Author.objects.get(username="localuser")
        self.client.login(username="localuser", password="pass1")

        self.remote_fqid = "https://remote.example/social_distribution/api/authors/6ee4d6bb-40b4-4902-b31b-77d4be882d2f"

    @patch("social_distribution.views.send_follow_to_inbox")
    def test_put_following_detail_creates_remote_author_and_sends_request(self, mock_send_follow):
        url = reverse(
            "social_distribution:api_author_following_detail",
            args=[self.local_author.serial, self.remote_fqid],
        )

        response = self.client.put(url, data={}, content_type="application/json")
        self.assertIn(response.status_code, (200, 201))

        remote_author = Author.objects.get(id=self.remote_fqid)
        self.assertFalse(remote_author.is_local)
        self.assertTrue(Follow.objects.filter(follower=self.local_author, following=remote_author).exists())
        mock_send_follow.assert_called_once()

    @patch("social_distribution.views.remote_node_get_authors")
    def test_author_list_refreshes_remote_authors_from_nodes(self, mock_remote_authors):
        Node.objects.create(
            url="https://remote.example/social_distribution/",
            outgoing_username="out",
            outgoing_password="outpw",
            incoming_username="in",
            incoming_password="inpw",
            is_enabled=True,
        )

        remote_author = Author.objects.create(
            id="https://remote.example/social_distribution/api/authors/11111111-1111-4111-8111-111111111111",
            serial="11111111-1111-4111-8111-111111111111",
            username="remote-user",
            host="https://remote.example/social_distribution/api/",
            is_local=False,
            is_approved=True,
            name="Remote User",
        )
        mock_remote_authors.return_value = [remote_author]

        response = self.client.get(reverse("social_distribution:author_list"))
        self.assertEqual(response.status_code, 200)
        mock_remote_authors.assert_called()

