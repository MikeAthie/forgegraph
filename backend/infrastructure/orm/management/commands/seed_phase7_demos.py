"""
Seed Phase 7 demo workflows.

Creates three showcase graphs demonstrating ForgeGraph's capabilities:
1. Research Assistant - Parallel LLM calls, merge, synthesis
2. Email Drafting Agent - Human-in-the-loop approval
3. Data Extraction Agent - Conditional branching with optional human review
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max

from infrastructure.orm.models import Graph, GraphVersion, User

# Prompt templates embedded directly (matching built-in prompts from migration 0002)
RESEARCH_SUMMARY_PROMPT = """You are a research analyst tasked with summarizing findings on a specific topic.

## Topic
{{topic}}

## Source Material
{{source_material}}

## Instructions
1. Read through all the provided source material carefully
2. Identify the key themes, findings, and insights
3. Organize the information into a coherent summary
4. Highlight any conflicting viewpoints or gaps in the research
5. Provide actionable conclusions

## Output Format
Please structure your summary as follows:
- **Executive Summary** (2-3 sentences)
- **Key Findings** (bullet points)
- **Detailed Analysis** (organized by theme)
- **Conclusions & Recommendations**"""

COMPETITIVE_ANALYSIS_PROMPT = """You are a market research analyst conducting a competitive analysis.

## Product/Service
{{product_name}}

## Competitors to Analyze
{{competitors}}

## Instructions
Analyze each competitor focusing on:
1. Product/service offerings and features
2. Target market and positioning
3. Strengths and weaknesses

## Output Format
For each competitor, provide:
- **Company Overview**
- **Product Comparison** (vs our product)
- **SWOT Summary**
- **Competitive Threat Level** (High/Medium/Low)

Conclude with:
- **Overall Competitive Landscape Summary**
- **Strategic Recommendations**"""

SYNTHESIS_PROMPT = """You are tasked with synthesizing multiple research reports into a unified, comprehensive summary.

## Research Report A
{{research_a}}

## Research Report B
{{research_b}}

## Instructions
1. Read both research reports carefully
2. Identify common themes and complementary insights
3. Note any conflicting findings and explain the differences
4. Create a unified summary that captures the full picture
5. Provide actionable recommendations based on both reports

## Output Format
- **Unified Executive Summary** (3-4 sentences)
- **Combined Key Findings** (consolidated bullet points)
- **Synthesis of Insights** (where reports agree and complement each other)
- **Discrepancies** (any conflicting information)
- **Final Recommendations**"""

PROFESSIONAL_EMAIL_PROMPT = """You are a professional communication specialist drafting an email.

## Key Points to Convey
{{key_points}}

## Recipient Information
- **To**: {{recipient_name}}
- **Relationship**: {{relationship}}

## Tone
{{tone}}

## Instructions
1. Start with an appropriate greeting
2. State the purpose clearly in the opening
3. Present the key points logically
4. End with a clear call-to-action or next steps
5. Use an appropriate closing

## Output
Draft a professional email that is clear, concise, and action-oriented.

---

**Subject**: [Suggest an appropriate subject line]

**Email Body**:
[Draft the email here]"""

DATA_PARSER_PROMPT = """You are a data extraction specialist. Parse the unstructured text into structured JSON format.

## Input Text
{{input_text}}

## Desired Output Schema
Extract the following fields:
- name (string): Full name of the person
- email (string): Email address if present
- phone (string): Phone number if present
- company (string): Company or organization name
- role (string): Job title or role
- notes (string): Any additional relevant information

## Instructions
1. Analyze the input text to find the requested information
2. Extract and normalize each field
3. Use null for missing optional fields
4. Rate your confidence in the extraction

## Output
Return ONLY a JSON object in this exact format:

```json
{
  "extracted_data": {
    "name": "...",
    "email": "...",
    "phone": "...",
    "company": "...",
    "role": "...",
    "notes": "..."
  },
  "confidence": 85
}
```

The confidence field should be a number from 0-100 indicating how confident you are in the extraction accuracy."""


class Command(BaseCommand):
    help = "Seed Phase 7 demo workflows (Research Assistant, Email Agent, Data Extraction)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-email",
            type=str,
            default=None,
            help="Email of the user that should own the demo graphs (defaults to first user or demo user).",
        )
        parser.add_argument(
            "--owner-password",
            type=str,
            default="ForgeGraphDemo!12345",
            help="Password to use if a demo user is created.",
        )

    def handle(self, *args, **options):
        owner_email: str | None = options.get("owner_email")
        owner_password: str = options["owner_password"]

        # Get or create owner
        owner = self._get_or_create_owner(owner_email, owner_password)

        with transaction.atomic():
            # Create all three demo workflows
            self._create_research_assistant(owner)
            self._create_email_agent(owner)
            self._create_data_extraction_agent(owner)

        self.stdout.write(
            self.style.SUCCESS("Done. Three demo workflows created. Open /graphs to view them.")
        )

    def _get_or_create_owner(self, owner_email: str | None, owner_password: str) -> User:
        """Get existing user or create a demo user."""
        owner: User | None = None

        if owner_email:
            owner_email = owner_email.strip().lower()
            owner = User.objects.filter(email=owner_email).first()

        if owner is None:
            owner = User.objects.order_by("date_joined").first()

        if owner is None:
            demo_email = (owner_email or "demo@example.com").strip().lower()
            owner, _ = User.objects.get_or_create(email=demo_email)
            owner.set_password(owner_password)
            owner.save(update_fields=["password"])
            self.stdout.write(self.style.WARNING(f"Created demo user {owner.email}"))
            self.stdout.write(self.style.WARNING(f"Demo password: {owner_password}"))

        return owner

    def _create_graph_version(
        self, owner: User, name: str, description: str, graph_json: dict
    ) -> GraphVersion:
        """Create a graph and its first version."""
        graph = Graph.objects.create(
            owner=owner,
            name=name,
            description=description,
        )
        latest_version = (
            GraphVersion.objects.filter(graph=graph)
            .aggregate(Max("version"))
            .get("version__max")
            or 0
        )
        version = GraphVersion.objects.create(
            graph=graph,
            version=latest_version + 1,
            graph_json=graph_json,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created '{name}' (graph={graph.id}, version={version.id})"
            )
        )
        return version

    def _create_research_assistant(self, owner: User) -> None:
        """
        Research Assistant Demo - Parallel research branches merged into synthesis.

        Graph structure:
        [Prompt A: Research] ----\
                                  ---> [Merge] ---> [Prompt: Synthesize] ---> [Output]
        [Prompt B: Competitive] -/
        """
        graph_json = {
            "metadata": {
                "name": "Research Assistant Demo",
                "description": "Parallel research on a topic, combining multiple sources into one report.",
            },
            "nodes": [
                {
                    "id": "research_summary",
                    "type": "prompt",
                    "name": "Research Summary",
                    "config": {
                        "prompt_template": RESEARCH_SUMMARY_PROMPT,
                        "system_prompt": "You are a thorough research analyst.",
                        "model": "gpt-4",
                        "temperature": 0.3,
                        "max_tokens": 1500,
                    },
                },
                {
                    "id": "competitive_analysis",
                    "type": "prompt",
                    "name": "Competitive Analysis",
                    "config": {
                        "prompt_template": COMPETITIVE_ANALYSIS_PROMPT,
                        "system_prompt": "You are a market research expert.",
                        "model": "gpt-4",
                        "temperature": 0.3,
                        "max_tokens": 1500,
                    },
                },
                {
                    "id": "merge_research",
                    "type": "merge",
                    "name": "Merge Research",
                    "config": {
                        "strategy": "namespaced",
                    },
                },
                {
                    "id": "synthesize",
                    "type": "prompt",
                    "name": "Synthesize Reports",
                    "config": {
                        "prompt_template": SYNTHESIS_PROMPT,
                        "system_prompt": "You are an expert at synthesizing multiple research sources.",
                        "model": "gpt-4",
                        "temperature": 0.4,
                        "max_tokens": 2000,
                    },
                },
                {
                    "id": "output",
                    "type": "output",
                    "name": "Final Report",
                    "config": {},
                },
            ],
            "edges": [
                {"id": "e1", "from": "research_summary", "to": "merge_research"},
                {"id": "e2", "from": "competitive_analysis", "to": "merge_research"},
                {"id": "e3", "from": "merge_research", "to": "synthesize"},
                {"id": "e4", "from": "synthesize", "to": "output"},
            ],
        }

        self._create_graph_version(
            owner,
            "Research Assistant Demo",
            "Parallel research on a topic, combining multiple sources into one comprehensive report. Demonstrates parallel LLM execution and merge synchronization.",
            graph_json,
        )

    def _create_email_agent(self, owner: User) -> None:
        """
        Email Drafting Agent - Draft email with human review.

        Graph structure:
        [Transform: Format] ---> [Prompt: Draft Email] ---> [Human Gate: Review] ---> [Output]
        """
        graph_json = {
            "metadata": {
                "name": "Email Drafting Agent",
                "description": "Draft a professional email with human review before sending.",
            },
            "nodes": [
                {
                    "id": "format_input",
                    "type": "transform",
                    "name": "Format Inputs",
                    "config": {
                        "expression": """
{
  "key_points": input.key_points or "Meeting follow-up and next steps",
  "recipient_name": input.recipient_name or "Team",
  "relationship": input.relationship or "colleague",
  "tone": input.tone or "professional"
}
""".strip(),
                    },
                },
                {
                    "id": "draft_email",
                    "type": "prompt",
                    "name": "Draft Email",
                    "config": {
                        "prompt_template": PROFESSIONAL_EMAIL_PROMPT,
                        "system_prompt": "You are an expert professional writer.",
                        "model": "gpt-4",
                        "temperature": 0.5,
                        "max_tokens": 1000,
                    },
                },
                {
                    "id": "human_review",
                    "type": "human_gate",
                    "name": "Review Email",
                    "config": {
                        "prompt_message": "Please review the drafted email. You can approve it as-is, or provide edits.",
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
                {"id": "e1", "from": "format_input", "to": "draft_email"},
                {"id": "e2", "from": "draft_email", "to": "human_review"},
                {"id": "e3", "from": "human_review", "to": "output"},
            ],
        }

        self._create_graph_version(
            owner,
            "Email Drafting Agent",
            "Draft a professional email with human-in-the-loop review before finalizing. Demonstrates transform, LLM generation, and human gate approval.",
            graph_json,
        )

    def _create_data_extraction_agent(self, owner: User) -> None:
        """
        Data Extraction Agent - Parse data with conditional human review.

        Graph structure:
                            true  --> [Human Gate: Verify] ---> [Output: Reviewed]
                           /
        [Prompt: Parse] ---> [Branch: confidence < 80?]
                           \
                            false --> [Output: Auto-Approved]
        """
        graph_json = {
            "metadata": {
                "name": "Data Extraction Agent",
                "description": "Extract structured data from text with optional human validation for low-confidence results.",
            },
            "nodes": [
                {
                    "id": "parse_data",
                    "type": "prompt",
                    "name": "Parse Data",
                    "config": {
                        "prompt_template": DATA_PARSER_PROMPT,
                        "system_prompt": "You are a precise data extraction specialist. Always output valid JSON.",
                        "model": "gpt-4",
                        "temperature": 0.1,
                        "max_tokens": 1000,
                    },
                },
                {
                    "id": "check_confidence",
                    "type": "branch",
                    "name": "Check Confidence",
                    "config": {
                        "condition": "vars.needs_review == true",
                    },
                },
                {
                    "id": "human_verify",
                    "type": "human_gate",
                    "name": "Human Verification",
                    "config": {
                        "prompt_message": "Low confidence extraction detected. Please review and correct the extracted data.",
                        "required_fields": ["corrected_data"],
                    },
                },
                {
                    "id": "output_reviewed",
                    "type": "output",
                    "name": "Output (Reviewed)",
                    "config": {},
                },
                {
                    "id": "output_auto",
                    "type": "output",
                    "name": "Output (Auto-Approved)",
                    "config": {},
                },
            ],
            "edges": [
                {"id": "e1", "from": "parse_data", "to": "check_confidence"},
                {"id": "e2", "from": "check_confidence", "to": "human_verify", "label": "true"},
                {"id": "e3", "from": "human_verify", "to": "output_reviewed"},
                {"id": "e4", "from": "check_confidence", "to": "output_auto", "label": "false"},
            ],
        }

        self._create_graph_version(
            owner,
            "Data Extraction Agent",
            "Extract structured information from unstructured text with conditional human review for low-confidence results. Demonstrates branching and human-in-the-loop validation.",
            graph_json,
        )
