import uuid

from django.db import migrations, models


def seed_graph_templates(apps, schema_editor):
    GraphTemplate = apps.get_model("orm", "GraphTemplate")
    if GraphTemplate.objects.exists():
        return

    templates = [
        {
            "name": "Investor Update Email (Human Gate)",
            "description": "Draft an investor update and require human approval before sending.",
            "category": "communication",
            "tags": ["human-gate", "email", "demo"],
            "estimated_minutes": 3,
            "sample_input": {
                "key_points": "Q1 revenue +28% YoY, churn down to 2.1%, launched v2 onboarding",
                "recipient_name": "Investors",
                "relationship": "stakeholder",
                "tone": "confident and concise",
            },
            "graph_json": {
                "metadata": {
                    "name": "Investor Update Email",
                    "description": "Generate an investor update draft with human approval.",
                },
                "nodes": [
                    {
                        "id": "draft_email",
                        "type": "prompt",
                        "name": "Draft Email",
                        "config": {
                            "prompt_template": (
                                "You are drafting an investor update email.\n\n"
                                "Key points:\n{{input.key_points}}\n\n"
                                "Recipient: {{input.recipient_name}}\n"
                                "Relationship: {{input.relationship}}\n"
                                "Tone: {{input.tone}}\n\n"
                                "Write a clear update with a short subject line and 3-5 bullet points."
                            ),
                            "system_prompt": "You are a sharp, concise communications lead.",
                            "model": "gpt-4",
                            "temperature": 0.4,
                            "max_tokens": 800,
                        },
                    },
                    {
                        "id": "human_review",
                        "type": "human_gate",
                        "name": "Review Email",
                        "config": {
                            "prompt_message": "Review the draft. Approve as-is or provide edits.",
                            "required_fields": ["approved", "edited_content"],
                        },
                    },
                    {
                        "id": "output",
                        "type": "output",
                        "name": "Final Email",
                        "config": {},
                    },
                ],
                "edges": [
                    {"id": "e1", "from": "draft_email", "to": "human_review"},
                    {"id": "e2", "from": "human_review", "to": "output"},
                ],
            },
        },
        {
            "name": "Research Brief",
            "description": "Summarize a topic into a crisp executive brief.",
            "category": "research",
            "tags": ["summary", "demo"],
            "estimated_minutes": 2,
            "sample_input": {
                "topic": "AI workflow automation for mid-market teams",
                "source_material": "Key trends: buyers want guardrails, quick onboarding, and observable runs.",
            },
            "graph_json": {
                "metadata": {
                    "name": "Research Brief",
                    "description": "Summarize source material into a research brief.",
                },
                "nodes": [
                    {
                        "id": "research_summary",
                        "type": "prompt",
                        "name": "Research Summary",
                        "config": {
                            "prompt_template": (
                                "Create an executive research brief.\n\n"
                                "Topic: {{input.topic}}\n\n"
                                "Source material:\n{{input.source_material}}\n\n"
                                "Output:\n- Executive summary (2-3 sentences)\n"
                                "- 4 bullet key findings\n- 1 recommended next step"
                            ),
                            "system_prompt": "You are a rigorous research analyst.",
                            "model": "gpt-4",
                            "temperature": 0.3,
                            "max_tokens": 700,
                        },
                    },
                    {
                        "id": "output",
                        "type": "output",
                        "name": "Brief",
                        "config": {},
                    },
                ],
                "edges": [
                    {"id": "e1", "from": "research_summary", "to": "output"},
                ],
            },
        },
        {
            "name": "Customer FAQ Generator",
            "description": "Generate FAQs from a product description.",
            "category": "product",
            "tags": ["faq", "demo"],
            "estimated_minutes": 2,
            "sample_input": {
                "product_description": "ForgeGraph helps teams build, run, and monitor AI workflows with real-time controls.",
            },
            "graph_json": {
                "metadata": {
                    "name": "Customer FAQ Generator",
                    "description": "Generate an FAQ set from product notes.",
                },
                "nodes": [
                    {
                        "id": "faq_prompt",
                        "type": "prompt",
                        "name": "FAQ Draft",
                        "config": {
                            "prompt_template": (
                                "Generate 6 concise FAQs for this product:\n{{input.product_description}}\n\n"
                                "Each FAQ should include a short question and 2-3 sentence answer."
                            ),
                            "system_prompt": "You write crisp product FAQs.",
                            "model": "gpt-4",
                            "temperature": 0.5,
                            "max_tokens": 600,
                        },
                    },
                    {
                        "id": "output",
                        "type": "output",
                        "name": "FAQ Output",
                        "config": {},
                    },
                ],
                "edges": [
                    {"id": "e1", "from": "faq_prompt", "to": "output"},
                ],
            },
        },
    ]

    for idx, template in enumerate(templates):
        GraphTemplate.objects.create(
            id=uuid.uuid4(),
            name=template["name"],
            description=template["description"],
            category=template["category"],
            tags=template["tags"],
            estimated_minutes=template["estimated_minutes"],
            graph_json=template["graph_json"],
            sample_input=template["sample_input"],
            display_order=idx + 1,
            is_active=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0019_llm_usage_budget"),
    ]

    operations = [
        migrations.CreateModel(
            name="GraphTemplate",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("category", models.CharField(blank=True, default="", max_length=64)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("estimated_minutes", models.PositiveIntegerField(default=3)),
                ("graph_json", models.JSONField()),
                ("sample_input", models.JSONField(blank=True, default=dict)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "graph_templates",
                "ordering": ["display_order", "name"],
            },
        ),
        migrations.AddIndex(
            model_name="graphtemplate",
            index=models.Index(
                fields=["is_active", "display_order"], name="graph_templates_active_idx"
            ),
        ),
        migrations.RunPython(seed_graph_templates, migrations.RunPython.noop),
    ]
