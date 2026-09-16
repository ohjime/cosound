from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse

from core.discussion import build_discussion_context
from core.models import Comment, PlayerProgram, Manager, Player, Sound, Post


class PlayerProgramAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="post-admin", email="post-admin@example.com", password="pw"
        )
        cls.manager = Manager.objects.create(user=cls.admin, name="Post manager")
        cls.player = Player.objects.create(manager=cls.manager, name="Garden player")
        cls.sound = Sound.objects.create(
            file="sounds/garden.wav", title="Garden birds", embeddings=[0, 0, 0, 0, 0]
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def post_fields(self, **overrides):
        return {
            "announcers_call": "Now sharing",
            "title": "Garden writing",
            "greeting_style": "Dear Listener",
            "font_family": "newsreader",
            "article": "Listen to the **garden**.",
            "authors_present": "1",
            "authors_name": ["Garden author"],
            "authors_role": ["Writer"],
            "authors_url": ["https://example.com/garden"],
            "composer": str(self.admin.pk),
            **overrides,
        }

    def player_fields(self, **overrides):
        return {
            "name": self.player.name,
            "bio": self.player.bio,
            "manager": self.manager.pk,
            "location": self.player.location,
            "sleeping": "on",
            "state_refresh_interval_seconds": 30,
            **overrides,
        }

    def program_fields(self, **overrides):
        return {
            "post": self.player.program.post_id,
            "collection": [],
            "algorithm_refresh_interval_seconds": 30,
            "algorithm_active_listener_minutes": 5,
            "algorithm_sleep_after_minutes": 180,
            "algorithm_min_layers": 2,
            "algorithm_max_layers": 5,
            "algorithm_minimum_hold_seconds": 120,
            "algorithm_maximum_stay_seconds": 180,
            "algorithm_disagreement_penalty": 0.25,
            "algorithm_exploration_probability": 0.5,
            "algorithm_exploration_size": 5,
            "baseline": "",
            **overrides,
        }

    def test_add_page_exposes_shared_writing_and_local_collection(self):
        response = self.client.get(reverse("admin:core_post_add"))

        self.assertContains(response, static("core/vendor/easymde.min.js"))
        self.assertContains(response, "data-authors-widget")
        self.assertContains(response, 'id="id_font_family"')
        self.assertNotContains(response, 'id="id_cosound"')
        self.assertNotContains(response, 'id="id_publication_date"')
        response = self.client.get(reverse("admin:core_playerprogram_add"))
        self.assertContains(response, 'id="id_post"')
        self.assertContains(response, 'id="id_collection"')

    def test_add_saves_shared_writing_and_collection_and_publishes_without_cosound(self):
        response = self.client.post(
            reverse("admin:core_post_add"),
            self.post_fields(_publish="1"),
        )

        self.assertEqual(response.status_code, 302)
        shared = Post.objects.get(title="Garden writing")
        response = self.client.post(
            reverse("admin:core_playerprogram_add"),
            self.program_fields(post=shared.pk, collection=[self.sound.pk]),
        )
        self.assertEqual(response.status_code, 302)
        post = PlayerProgram.objects.get(post=shared)
        self.assertEqual(post.post.article, "Listen to the **garden**.")
        self.assertEqual(post.post.font_family, "newsreader")
        self.assertEqual(post.post.authors, [
            {"name": "Garden author", "role": "Writer", "url": "https://example.com/garden"}
        ])
        self.assertEqual(list(post.collection.all()), [self.sound])
        self.assertIsNotNone(post.post.publication_date)

    def test_existing_program_can_publish_with_an_empty_collection(self):
        post = PlayerProgram.objects.create(post=Post.objects.create(title="Draft", composer=self.admin))

        response = self.client.post(
            reverse("admin:core_post_change", args=[post.post_id]),
            self.post_fields(_publish="1"),
        )

        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertIsNotNone(post.post.publication_date)
        self.assertFalse(post.collection.exists())

    def test_player_editor_links_to_its_post_and_uses_a_post_picker(self):
        response = self.client.get(
            reverse("admin:core_player_change", args=[self.player.pk])
        )

        self.assertContains(response, 'id="id_program"')
        self.assertContains(
            response,
            reverse("admin:core_playerprogram_change", args=[self.player.program_id]),
        )
        self.assertContains(response, "writing and sound collection")
        self.assertNotContains(response, 'id="id_sounds"')

    def test_player_add_can_omit_the_post_and_receive_an_editable_program(self):
        response = self.client.post(
            reverse("admin:core_player_add"),
            self.player_fields(
                name="New player",
                bio="New writing",
                program="",
            ),
        )

        self.assertEqual(response.status_code, 302)
        player = Player.objects.get(name="New player")
        self.assertEqual(player.program.post.title, "New player")
        self.assertEqual(player.program.post.article, "New writing")
        self.assertEqual(player.program.post.composer, self.admin)

    def test_player_editor_can_assign_a_different_program(self):
        replacement = PlayerProgram.objects.create(post=Post.objects.create(title="Replacement", composer=self.admin))
        original_id = self.player.program_id

        response = self.client.post(
            reverse("admin:core_player_change", args=[self.player.pk]),
            self.player_fields(program=replacement.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.player.refresh_from_db()
        self.assertEqual(self.player.program, replacement)
        self.assertTrue(PlayerProgram.objects.filter(pk=original_id).exists())


class SharedDiscussionContextTests(TestCase):
    def test_pagination_preserves_player_route_and_replaces_existing_page(self):
        composer = get_user_model().objects.create_user(
            username="discussion-composer", email="discussion-composer@example.com"
        )
        program = PlayerProgram.objects.create(post=Post.objects.create(title="A local discussion", composer=composer))
        for index in range(11):
            listener = get_user_model().objects.create_user(
                username=f"discussion-listener-{index}",
                email=f"discussion-listener-{index}@example.com",
            )
            Comment.objects.create(post=program.post, user=listener, body=f"Response {index}")
        discussion_url = "/vote/comments/?player=token&choice=up&section=water&page=1#discussion"

        context = build_discussion_context(
            program.post, composer,
            discussion_url=discussion_url,
            comment_url="/vote/comments/new/?player=token&section=water",
            dom_id="player-discussion",
        )

        second_page = next(item for item in context["pagination_items"] if item.get("number") == 2)
        url = urlsplit(second_page["url"])
        self.assertEqual(url.path, "/vote/comments/")
        self.assertEqual(url.fragment, "discussion")
        self.assertEqual(parse_qs(url.query), {
            "player": ["token"], "choice": ["up"], "section": ["water"], "page": ["2"]
        })
        self.assertEqual(context["post"], program.post)
        self.assertEqual(context["comment_count"], 11)
        self.assertEqual(context["dom_id"], "player-discussion")
