import pytest

from infrastructure.orm.models import Graph, GraphVersion, PromptTemplate, User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_builtin_prompts():
    """Remove built-in prompts seeded by migrations to ensure clean test state."""
    PromptTemplate.objects.filter(owner__isnull=True).delete()
    yield


def test_graph_manager_for_user_filters_by_owner(user):
    other_user = User.objects.create_user(email="other@example.com", password="testpassword123")
    Graph.objects.create(owner=user, name="Mine", description="")
    Graph.objects.create(owner=other_user, name="Theirs", description="")

    graphs = Graph.objects.for_user(user)

    assert graphs.count() == 1
    assert graphs.first().name == "Mine"


def test_graph_version_manager_latest_for_graph_returns_highest_version(user):
    graph = Graph.objects.create(owner=user, name="G", description="")
    GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    GraphVersion.objects.create(
        graph=graph,
        version=2,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )

    latest = GraphVersion.objects.latest_for_graph(graph.id)

    assert latest is not None
    assert latest.version == 2


def test_prompt_template_manager_public_filters_visibility(user):
    other_user = User.objects.create_user(email="other@example.com", password="testpassword123")
    PromptTemplate.objects.create(
        owner=None,
        title="Builtin",
        description="",
        category="other",
        content="hi",
        variables_schema={},
        visibility="public",
    )
    PromptTemplate.objects.create(
        owner=user,
        title="Mine Private",
        description="",
        category="other",
        content="hi",
        variables_schema={},
        visibility="private",
    )
    PromptTemplate.objects.create(
        owner=other_user,
        title="Theirs Public",
        description="",
        category="other",
        content="hi",
        variables_schema={},
        visibility="public",
    )

    public_titles = set(PromptTemplate.objects.public().values_list("title", flat=True))
    assert public_titles == {"Builtin", "Theirs Public"}


def test_prompt_template_manager_for_user_includes_owner_and_public(user):
    other_user = User.objects.create_user(email="other@example.com", password="testpassword123")
    PromptTemplate.objects.create(
        owner=None,
        title="Builtin",
        description="",
        category="other",
        content="hi",
        variables_schema={},
        visibility="public",
    )
    PromptTemplate.objects.create(
        owner=user,
        title="Mine Private",
        description="",
        category="other",
        content="hi",
        variables_schema={},
        visibility="private",
    )
    PromptTemplate.objects.create(
        owner=other_user,
        title="Theirs Public",
        description="",
        category="other",
        content="hi",
        variables_schema={},
        visibility="public",
    )
    PromptTemplate.objects.create(
        owner=other_user,
        title="Theirs Private",
        description="",
        category="other",
        content="hi",
        variables_schema={},
        visibility="private",
    )

    visible_titles = set(PromptTemplate.objects.for_user(user).values_list("title", flat=True))
    assert visible_titles == {"Builtin", "Mine Private", "Theirs Public"}


def test_prompt_template_clone_for_user_creates_private_copy(user):
    original = PromptTemplate.objects.create(
        owner=None,
        title="Original",
        description="desc",
        category="other",
        content="content",
        variables_schema={"nested": {"a": 1}},
        visibility="public",
    )

    clone = original.clone_for_user(user)

    assert clone.owner == user
    assert clone.visibility == "private"
    assert clone.title == "Original (Copy)"
    assert clone.variables_schema == {"nested": {"a": 1}}
    assert clone.variables_schema is not original.variables_schema

    original.variables_schema["nested"]["a"] = 2
    assert clone.variables_schema["nested"]["a"] == 1
