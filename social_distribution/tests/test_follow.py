from django.test import TestCase, Client
from django.urls import reverse
from social_distribution.models import Author, Follow, TextEntry
from django.contrib.auth.models import User
from social_distribution.views import friends

class FollowingAuthorsTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="user1", password="pass1")
        self.user1 = User.objects.create_user(username="user2", password="pass2")
        self.user1 = User.objects.create_user(username="user3", password="pass3")

        self.author1 = Author.objects.create(url="user1", name="user 1")
        self.author2 = Author.objects.create(url="user2", name="user 2")
        self.author3 = Author.objects.create(url="user3", name="user 3")

        self.client = Client()
    
    def test_follow_request_approval(self):
        #user2 follows user1
        self.client.login(username='user2', password='pass2')
        response = self.client.get(reverse('social_distribution:follow_author', args=['user1']))
        self.assertEqual(response.status_code, 302)

        #check that follow request exists and not approved
        follow_request = Follow.objects.get(follower=self.author2, following=self.author1)
        self.assertFalse(follow_request.approved)

        #user1 approves follow request
        self.client.login(username='user1', password='pass1')
        response = self.client.get(reverse('social_distribution:approve_follow', args=['user2']))
        follow_request.refresh_from_db()
        self.assertTrue(follow_request.approved)

    def test_unfollow(self):
        #user2 follows user1
        Follow.objects.create(follower=self.author2, following=self.author1, approved=True)

        self.client.login(username='user2', password='pass2')
        response = self.client.get(reverse('social_distribution:unfollow', args=['user1']))
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
        friends_entry = TextEntry.objects.create(
            belonging_url='user1',
            entry_text='Friends only post',
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
        
