"""
Data migration to seed built-in prompt templates.

These are system prompts available to all users (owner=None, visibility='public').
"""

from django.db import migrations

BUILTIN_PROMPTS = [
    # Research Category
    {
        "title": "Research Summary",
        "description": "Summarize research findings on a topic into a comprehensive overview with key insights and conclusions.",
        "category": "research",
        "content": """You are a research analyst tasked with summarizing findings on a specific topic.

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
- **Limitations & Gaps**
- **Conclusions & Recommendations**""",
        "variables_schema": {
            "topic": {
                "type": "string",
                "description": "The research topic to summarize",
                "required": True,
            },
            "source_material": {
                "type": "string",
                "description": "The research content to analyze",
                "required": True,
            },
        },
    },
    {
        "title": "Competitive Analysis",
        "description": "Analyze competitors for a product or service, identifying strengths, weaknesses, and market positioning.",
        "category": "research",
        "content": """You are a market research analyst conducting a competitive analysis.

## Product/Service
{{product_name}}

## Competitors to Analyze
{{competitors}}

## Market Context
{{market_context}}

## Instructions
Analyze each competitor focusing on:
1. Product/service offerings and features
2. Pricing strategy
3. Target market and positioning
4. Strengths and weaknesses
5. Market share (if known)
6. Recent developments or trends

## Output Format
For each competitor, provide:
- **Company Overview**
- **Product Comparison** (vs our product)
- **Pricing Analysis**
- **SWOT Summary**
- **Competitive Threat Level** (High/Medium/Low)

Conclude with:
- **Overall Competitive Landscape Summary**
- **Strategic Recommendations**""",
        "variables_schema": {
            "product_name": {
                "type": "string",
                "description": "Your product or service name",
                "required": True,
            },
            "competitors": {
                "type": "string",
                "description": "List of competitors to analyze",
                "required": True,
            },
            "market_context": {
                "type": "string",
                "description": "Additional market context or industry information",
                "required": False,
            },
        },
    },
    # Summarization Category
    {
        "title": "Document Summary",
        "description": "Summarize a long document into key points, main arguments, and essential takeaways.",
        "category": "summarization",
        "content": """You are a professional summarizer. Your task is to distill a long document into its essential points.

## Document
{{document}}

## Summary Length
{{summary_length}}

## Instructions
1. Read the entire document carefully
2. Identify the main thesis or purpose
3. Extract key arguments and supporting evidence
4. Note any important data, statistics, or quotes
5. Preserve the original meaning and intent

## Output Format
- **Document Type**: [Report/Article/Paper/etc.]
- **Main Purpose**: [1-2 sentences]
- **Key Points**:
  1. [Point 1]
  2. [Point 2]
  3. [Point 3]
  (continue as needed)
- **Important Details**: [Any crucial data or quotes]
- **Conclusion**: [Main takeaway in 2-3 sentences]""",
        "variables_schema": {
            "document": {
                "type": "string",
                "description": "The full document text to summarize",
                "required": True,
            },
            "summary_length": {
                "type": "string",
                "description": "Desired summary length (brief/medium/detailed)",
                "required": False,
                "default": "medium",
            },
        },
    },
    {
        "title": "Meeting Notes",
        "description": "Convert a meeting transcript into structured notes with action items and decisions.",
        "category": "summarization",
        "content": """You are an executive assistant converting a meeting transcript into structured notes.

## Meeting Transcript
{{transcript}}

## Meeting Context
{{meeting_context}}

## Instructions
1. Identify all participants and their roles
2. Extract key discussion points
3. Document all decisions made
4. List action items with owners and deadlines
5. Note any unresolved issues or follow-ups needed

## Output Format

### Meeting Information
- **Date**: [Extract from transcript or use today]
- **Attendees**: [List all participants]
- **Meeting Type**: {{meeting_type}}

### Summary
[2-3 sentence overview of the meeting]

### Discussion Points
1. **[Topic 1]**
   - Key points discussed
   - Decisions made

2. **[Topic 2]**
   - Key points discussed
   - Decisions made

### Action Items
| Action | Owner | Deadline | Status |
|--------|-------|----------|--------|
| [Action 1] | [Name] | [Date] | Pending |

### Decisions Made
- [Decision 1]
- [Decision 2]

### Open Items / Follow-ups
- [Item requiring follow-up]

### Next Steps
[What happens next]""",
        "variables_schema": {
            "transcript": {
                "type": "string",
                "description": "The meeting transcript or notes",
                "required": True,
            },
            "meeting_context": {
                "type": "string",
                "description": "Context about the meeting purpose",
                "required": False,
            },
            "meeting_type": {
                "type": "string",
                "description": "Type of meeting (standup, planning, review, etc.)",
                "required": False,
                "default": "General",
            },
        },
    },
    # Email Category
    {
        "title": "Professional Email",
        "description": "Draft a professional email from key points and context.",
        "category": "email",
        "content": """You are a professional communication specialist drafting an email.

## Key Points to Convey
{{key_points}}

## Recipient Information
- **To**: {{recipient_name}}
- **Relationship**: {{relationship}}

## Email Context
{{context}}

## Tone
{{tone}}

## Instructions
1. Start with an appropriate greeting
2. State the purpose clearly in the opening
3. Present the key points logically
4. Include any necessary context or background
5. End with a clear call-to-action or next steps
6. Use an appropriate closing

## Output
Draft a professional email that is:
- Clear and concise
- Appropriately formal for the relationship
- Action-oriented
- Free of jargon unless industry-appropriate

---

**Subject**: [Suggest an appropriate subject line]

**Email Body**:
[Draft the email here]""",
        "variables_schema": {
            "key_points": {
                "type": "string",
                "description": "Main points to include in the email",
                "required": True,
            },
            "recipient_name": {
                "type": "string",
                "description": "Name of the email recipient",
                "required": True,
            },
            "relationship": {
                "type": "string",
                "description": "Your relationship (colleague, client, manager, etc.)",
                "required": True,
            },
            "context": {
                "type": "string",
                "description": "Additional context for the email",
                "required": False,
            },
            "tone": {
                "type": "string",
                "description": "Desired tone (formal, friendly, urgent, etc.)",
                "required": False,
                "default": "professional",
            },
        },
    },
    {
        "title": "Follow-up Email",
        "description": "Generate a follow-up email after a meeting or conversation.",
        "category": "email",
        "content": """You are drafting a follow-up email after a meeting or conversation.

## Meeting/Conversation Summary
{{meeting_summary}}

## Key Outcomes
{{outcomes}}

## Action Items
{{action_items}}

## Recipient
{{recipient_name}}

## Instructions
1. Thank them for their time
2. Recap the key discussion points briefly
3. Confirm any decisions or agreements
4. List action items with clear ownership
5. Propose next steps or timeline
6. Offer to clarify anything if needed

## Output

**Subject**: [Suggest subject line, e.g., "Follow-up: [Meeting Topic]"]

**Email Body**:
[Draft a professional follow-up email that:
- Opens with appreciation
- Summarizes key points concisely
- Clearly states action items
- Sets expectations for next steps
- Closes professionally]""",
        "variables_schema": {
            "meeting_summary": {
                "type": "string",
                "description": "Brief summary of what was discussed",
                "required": True,
            },
            "outcomes": {
                "type": "string",
                "description": "Key decisions or outcomes from the meeting",
                "required": True,
            },
            "action_items": {
                "type": "string",
                "description": "List of action items and owners",
                "required": False,
            },
            "recipient_name": {
                "type": "string",
                "description": "Name of the person you met with",
                "required": True,
            },
        },
    },
    # Extraction Category
    {
        "title": "Entity Extraction",
        "description": "Extract named entities (people, organizations, locations, dates, etc.) from text.",
        "category": "extraction",
        "content": """You are a named entity recognition specialist. Extract all relevant entities from the provided text.

## Text to Analyze
{{text}}

## Entity Types to Extract
{{entity_types}}

## Instructions
1. Read the text carefully
2. Identify all named entities matching the requested types
3. For each entity, note where it appears (context)
4. Resolve any coreferences (e.g., "he" refers to "John Smith")
5. Remove duplicates and normalize names

## Output Format

### Extracted Entities

**People**:
- [Name] - [Role/Context if mentioned]

**Organizations**:
- [Organization Name] - [Type: Company/Government/NGO/etc.]

**Locations**:
- [Location] - [Type: City/Country/Address/etc.]

**Dates/Times**:
- [Date/Time] - [Context]

**Monetary Values**:
- [Amount] - [Context]

**Other Entities**:
- [Entity] - [Type] - [Context]

### Entity Relationships
[Note any relationships between entities mentioned in the text]

### Summary
[Brief summary of what the text is about based on the entities found]""",
        "variables_schema": {
            "text": {
                "type": "string",
                "description": "The text to extract entities from",
                "required": True,
            },
            "entity_types": {
                "type": "string",
                "description": "Types of entities to extract (people, orgs, locations, dates, etc.)",
                "required": False,
                "default": "all",
            },
        },
    },
    {
        "title": "Data Parser",
        "description": "Parse unstructured text into structured JSON format.",
        "category": "extraction",
        "content": """You are a data extraction specialist. Parse the unstructured text into a structured JSON format.

## Input Text
{{input_text}}

## Desired Output Schema
{{output_schema}}

## Instructions
1. Analyze the input text to understand its structure
2. Map the information to the desired output schema
3. Handle missing fields appropriately (null or default values)
4. Normalize data formats (dates, numbers, etc.)
5. Validate the output matches the schema

## Rules
- Use null for missing optional fields
- Use consistent date format: YYYY-MM-DD
- Use consistent number formats (no currency symbols in numeric fields)
- Preserve original text for free-form fields
- Flag any parsing uncertainties

## Output

```json
{
  // Your structured JSON output here
}
```

### Parsing Notes
- **Confidence Level**: [High/Medium/Low]
- **Fields Requiring Review**: [List any fields with uncertain parsing]
- **Missing Information**: [List any expected fields not found in source]""",
        "variables_schema": {
            "input_text": {
                "type": "string",
                "description": "The unstructured text to parse",
                "required": True,
            },
            "output_schema": {
                "type": "string",
                "description": "Description or example of the desired JSON structure",
                "required": True,
            },
        },
    },
    # Reasoning Category
    {
        "title": "Decision Analysis",
        "description": "Analyze pros and cons for a decision, providing a structured evaluation.",
        "category": "reasoning",
        "content": """You are a decision analysis expert helping evaluate options for an important decision.

## Decision to Make
{{decision}}

## Options to Consider
{{options}}

## Context and Constraints
{{context}}

## Key Criteria
{{criteria}}

## Instructions
1. Understand the decision context and constraints
2. Evaluate each option against the criteria
3. Identify pros and cons for each option
4. Consider short-term and long-term implications
5. Assess risks and mitigation strategies
6. Provide a clear recommendation

## Output Format

### Decision Overview
[Restate the decision in clear terms]

### Evaluation Criteria
| Criterion | Weight | Description |
|-----------|--------|-------------|
| [Criterion 1] | [1-5] | [Why it matters] |

### Option Analysis

#### Option 1: [Name]
**Pros:**
- [Pro 1]
- [Pro 2]

**Cons:**
- [Con 1]
- [Con 2]

**Risk Assessment**: [Low/Medium/High]
**Score**: [X/10]

[Repeat for each option]

### Comparison Matrix
| Criterion | Option 1 | Option 2 | Option 3 |
|-----------|----------|----------|----------|
| [Criterion] | [Score] | [Score] | [Score] |

### Recommendation
**Recommended Option**: [Option Name]

**Rationale**: [2-3 sentences explaining why]

**Implementation Considerations**: [Key things to consider if proceeding]

**Risks to Monitor**: [What could go wrong and how to mitigate]""",
        "variables_schema": {
            "decision": {
                "type": "string",
                "description": "The decision you need to make",
                "required": True,
            },
            "options": {
                "type": "string",
                "description": "The options you are considering",
                "required": True,
            },
            "context": {
                "type": "string",
                "description": "Relevant context, constraints, or background",
                "required": False,
            },
            "criteria": {
                "type": "string",
                "description": "Key criteria for evaluating options",
                "required": False,
            },
        },
    },
    {
        "title": "Step-by-Step Solver",
        "description": "Break down a complex problem into logical steps and solve it methodically.",
        "category": "reasoning",
        "content": """You are a problem-solving expert. Break down the problem into steps and solve it methodically.

## Problem Statement
{{problem}}

## Known Information
{{known_info}}

## Constraints
{{constraints}}

## Instructions
1. Understand the problem completely before solving
2. Identify what is being asked
3. Break down into smaller sub-problems
4. Solve each step showing your reasoning
5. Verify your solution makes sense
6. Summarize the approach and answer

## Output Format

### Problem Understanding
**What we're solving**: [Restate in your own words]
**Type of problem**: [Category: Math/Logic/Planning/Technical/etc.]
**Key constraints**: [List constraints that affect the solution]

### Step-by-Step Solution

**Step 1: [Step Name]**
- What we're doing: [Explanation]
- Work: [Show your work]
- Result: [Intermediate result]

**Step 2: [Step Name]**
- What we're doing: [Explanation]
- Work: [Show your work]
- Result: [Intermediate result]

[Continue for all steps]

### Verification
- Check 1: [Verify aspect 1]
- Check 2: [Verify aspect 2]

### Final Answer
**Solution**: [Clear statement of the answer]

**Confidence**: [High/Medium/Low]

**Alternative Approaches**: [If applicable, mention other ways to solve]

### Key Insights
[What made this problem solvable? What's the key insight?]""",
        "variables_schema": {
            "problem": {
                "type": "string",
                "description": "The problem to solve",
                "required": True,
            },
            "known_info": {
                "type": "string",
                "description": "Information or data provided",
                "required": False,
            },
            "constraints": {
                "type": "string",
                "description": "Any constraints or limitations",
                "required": False,
            },
        },
    },
]


def create_builtin_prompts(apps, schema_editor):
    """Create the built-in prompt templates."""
    PromptTemplate = apps.get_model("orm", "PromptTemplate")

    for prompt_data in BUILTIN_PROMPTS:
        PromptTemplate.objects.create(
            owner=None,  # Built-in prompts have no owner
            title=prompt_data["title"],
            description=prompt_data["description"],
            category=prompt_data["category"],
            content=prompt_data["content"],
            variables_schema=prompt_data["variables_schema"],
            version="1.0.0",
            license="MIT",
            visibility="public",
        )


def remove_builtin_prompts(apps, schema_editor):
    """Remove the built-in prompt templates (for rollback)."""
    PromptTemplate = apps.get_model("orm", "PromptTemplate")
    titles = [p["title"] for p in BUILTIN_PROMPTS]
    PromptTemplate.objects.filter(owner__isnull=True, title__in=titles).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_builtin_prompts, remove_builtin_prompts),
    ]
