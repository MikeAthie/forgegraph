from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, '/app')

from application.services.career_ops_resume_formatter import render_career_ops_ats_resume

ROOT = Path('/app/.hermes') if Path('/app/.hermes').exists() else Path(__file__).resolve().parent
OUT_PDF = ROOT / 'codifin-final-review-cv.pdf'
OUT_TEXT = ROOT / 'codifin-final-review-cv-extracted-renderer-text.txt'
OUT_REPORT = ROOT / 'codifin-final-review-cv-parseability.json'

summary = (
    'Lead-capable full-stack/back-end engineer building SaaS-style products, data automation systems, and scalable backend services across '
    'Golang, React/Next.js, PostgreSQL, Python, and TypeScript. Experienced designing REST APIs, clean service boundaries, async/event-driven '
    'pipelines, and data handling with PostgreSQL and Redis. Hands-on integrating AI features (RAG/agent workflows) into real applications with '
    'grounding, orchestration, and reliability guardrails. Comfortable working in Linux/Git-based environments, collaborating with Product/QA and '
    'non-technical stakeholders, and owning delivery from requirements and architecture through reliable releases. Bilingual Spanish/English with '
    'Cambridge English C2 Proficiency certification.'
)

resume = {
    'status': 'draft',
    'format': 'codifin_final_review_v1',
    'opportunity': {
        'employer_name': 'Codifin',
        'role_title': 'Lead Golang & React Developer CDMX Bilingue',
        'job_url': 'https://mx.indeed.com/viewjob?jk=0ee36499821e9442',
    },
    'sections': [
        {'heading': 'SUMMARY', 'items': [summary]},
        {
            'heading': 'TECHNICAL SKILLS',
            'items': [
                'Full-Stack: React/Next.js, TypeScript, FastAPI, backend-first product delivery, API-driven workflows',
                'Backend & APIs: Golang, Python, REST API design, GraphQL-ready service boundaries, backend architecture, production reliability',
                'Data & Automation: PostgreSQL/SQL, Redis, data ingestion, async/event-driven pipelines, workflow automation, discrepancy detection',
                'SaaS & AI Integration: SaaS workflow design, RAG/agentic workflows, AI feature integration, grounding/reliability practices',
                'Tooling/Workflow: Docker, Linux-based development, Git, CI/CD practices, service-oriented patterns, iterative releases',
                'Collaboration: Product/QA collaboration, stakeholder requirements, bilingual Spanish/English communication, technical tradeoff explanation',
            ],
        },
        {
            'heading': 'SELECTED EXPERIENCE',
            'items': [
                {
                    'title': 'Grey Cross Developments',
                    'subtitle': 'Product Engineer',
                    'period': 'Jul 2022 - Present | CDMX',
                    'bullets': [
                        'Owned end-to-end backend and full-stack product domains for SMB products and consulting clients, from architecture and API contracts through production deployment and iteration.',
                        'Designed and implemented REST APIs and service boundaries for SaaS workflows, internal automation, and stakeholder-facing product features, prioritizing maintainability, clear contracts, and reliability.',
                        'Built async/event-driven and data-processing pipelines for real-time and batch workloads, improving responsiveness and operational robustness for data-heavy systems.',
                        'Implemented structured data handling with PostgreSQL and Redis patterns, supporting reporting, automation, and downstream operational decision-making.',
                        'Built React/Next.js and TypeScript product surfaces where frontend clarity, backend correctness, and API-driven workflows all mattered.',
                        'Integrated AI-powered features, RAG/agent workflows, and automated analysis into production-style systems with source-bounded behavior and predictable outputs.',
                        'Collaborated with Product, QA-style review, and non-technical stakeholders to translate requirements into deliverables and ship iterative improvements with production ownership.',
                    ],
                },
                {
                    'title': 'Vittahouse',
                    'subtitle': 'Automation & Data Consultant',
                    'period': 'Oct 2019 - Nov 2025 | CDMX',
                    'bullets': [
                        'Automated accounting and audit workflows, reducing manual steps and improving consistency across recurring operational processes.',
                        'Built discrepancy detection tooling across structured datasets to surface anomalies early and support audit readiness through traceable outputs.',
                        'Developed internal data/reporting foundations that improved decision-making speed, data quality, and operational visibility for finance/audit stakeholders.',
                        'Partnered with business users to gather requirements, define acceptance criteria, communicate tradeoffs, and deliver reliable workflow improvements.',
                    ],
                },
            ],
        },
        {
            'heading': 'PROJECTS',
            'items': [
                {
                    'title': 'ForgeGraph',
                    'subtitle': 'AI-powered SaaS/company OS for strategy automation',
                    'period': 'Nov 2025 - Present',
                    'url': 'https://github.com/MikeAthie/ForgeGraph',
                    'bullets': [
                        'Built an AI-powered company OS platform that analyzes competitor activity across social channels and turns it into actionable strategy insights.',
                        'Designed backend workflows for competitive strategy scraping, content analysis, report generation, durable workflow state, and scalable service expansion.',
                        'Integrated LLM-assisted analysis with source-bounded outputs, automation guardrails, and operator-review gates for reliable business intelligence workflows.',
                    ],
                },
                {
                    'title': 'Lex Toolkit',
                    'subtitle': 'AI agents for legal workflows (Next.js + FastAPI)',
                    'period': 'Nov 2025 - Present',
                    'url': 'https://github.com/MikeAthie/Lex-Toolkit',
                    'bullets': [
                        'Built a full-stack application with React/Next.js frontend and FastAPI backend, designed around API-driven professional workflows.',
                        'Developed AI agent capabilities for law-practice use cases, combining product UX, backend services, and grounded AI workflow design.',
                        'Designed clear API contracts and maintainable service boundaries to support real-world workflow expansion.',
                    ],
                },
                {
                    'title': 'Automated Trading Bot',
                    'subtitle': 'Real-time data automation (Redis + workers)',
                    'period': 'Aug 2025 - Present',
                    'url': 'https://github.com/MikeAthie/2m2',
                    'bullets': [
                        'Engineered a real-time pipeline consuming market data via WebSockets, persisting state in Redis, and processing indicators in a separate service.',
                        'Executed automated actions through worker-based architecture, emphasizing reliability and efficiency under continuous data flow.',
                        'Separated data ingestion, indicator computation, and execution concerns to improve throughput, maintainability, and operational resilience.',
                    ],
                },
            ],
        },
        {
            'heading': 'EDUCATION',
            'items': ['ITAM - Bachelor of Science in Law | 2012 - 2017 | CDMX | Focus on integrating technology, data systems, and professional practice.'],
        },
        {
            'heading': 'CERTIFICATIONS',
            'items': [
                'Cambridge English C2 Proficiency certificate',
                'Meta Back-End Developer (May 2023)',
                'IBM RAG and Agentic AI (May 2025)',
            ],
        },
    ],
    'quality': {'external_side_effects_allowed': False},
}

identity = {
    'name': 'Miguel Athie',
    'title': 'Lead Full-Stack / Back-End Engineer',
    'location': 'Mexico City (CDMX)',
    'email': 'miguel.athien@gmail.com',
    'phone': '+52 55 3900 3599',
    'github': 'GitHub: https://github.com/MikeAthie',
    'professional_summary': summary,
    'skills': [
        'Full-Stack: React/Next.js, TypeScript, FastAPI, backend-first product delivery, API-driven workflows',
        'Backend & APIs: Golang, Python, REST API design, GraphQL-ready service boundaries, backend architecture, production reliability',
        'Data & Automation: PostgreSQL/SQL, Redis, data ingestion, async/event-driven pipelines, workflow automation, discrepancy detection',
        'SaaS & AI Integration: SaaS workflow design, RAG/agentic workflows, AI feature integration, grounding/reliability practices',
        'Tooling/Workflow: Docker, Linux-based development, Git, CI/CD practices, service-oriented patterns, iterative releases',
        'Collaboration: Product/QA collaboration, stakeholder requirements, bilingual Spanish/English communication, technical tradeoff explanation',
    ],
    'experience': [
        {
            'company': 'Grey Cross Developments',
            'role': 'Product Engineer',
            'period': 'Jul 2022 - Present | CDMX',
            'bullets': [
                'Owned end-to-end backend and full-stack product domains for SMB products and consulting clients, from architecture and API contracts through production deployment and iteration.',
                'Designed and implemented REST APIs and service boundaries for SaaS workflows, internal automation, and stakeholder-facing product features, prioritizing maintainability, clear contracts, and reliability.',
                'Built async/event-driven and data-processing pipelines for real-time and batch workloads, improving responsiveness and operational robustness for data-heavy systems.',
                'Implemented structured data handling with PostgreSQL and Redis patterns, supporting reporting, automation, and downstream operational decision-making.',
                'Built React/Next.js and TypeScript product surfaces where frontend clarity, backend correctness, and API-driven workflows all mattered.',
                'Integrated AI-powered features, RAG/agent workflows, and automated analysis into production-style systems with source-bounded behavior and predictable outputs.',
                'Collaborated with Product, QA-style review, and non-technical stakeholders to translate requirements into deliverables and ship iterative improvements with production ownership.',
            ],
        },
        {
            'company': 'Vittahouse',
            'role': 'Automation & Data Consultant',
            'period': 'Oct 2019 - Nov 2025 | CDMX',
            'bullets': [
                'Automated accounting and audit workflows, reducing manual steps and improving consistency across recurring operational processes.',
                'Built discrepancy detection tooling across structured datasets to surface anomalies early and support audit readiness through traceable outputs.',
                'Developed internal data/reporting foundations that improved decision-making speed, data quality, and operational visibility for finance/audit stakeholders.',
                'Partnered with business users to gather requirements, define acceptance criteria, communicate tradeoffs, and deliver reliable workflow improvements.',
            ],
        },
    ],
    'projects': [
        {
            'name': 'ForgeGraph',
            'subtitle': 'AI-powered SaaS/company OS for strategy automation',
            'period': 'Nov 2025 - Present',
            'url': 'https://github.com/MikeAthie/ForgeGraph',
            'bullets': [
                'Built an AI-powered company OS platform that analyzes competitor activity across social channels and turns it into actionable strategy insights.',
                'Designed backend workflows for competitive strategy scraping, content analysis, report generation, durable workflow state, and scalable service expansion.',
                'Integrated LLM-assisted analysis with source-bounded outputs, automation guardrails, and operator-review gates for reliable business intelligence workflows.',
            ],
        },
        {
            'name': 'Lex Toolkit',
            'subtitle': 'AI agents for legal workflows (Next.js + FastAPI)',
            'period': 'Nov 2025 - Present',
            'url': 'https://github.com/MikeAthie/Lex-Toolkit',
            'bullets': [
                'Built a full-stack application with React/Next.js frontend and FastAPI backend, designed around API-driven professional workflows.',
                'Developed AI agent capabilities for law-practice use cases, combining product UX, backend services, and grounded AI workflow design.',
                'Designed clear API contracts and maintainable service boundaries to support real-world workflow expansion.',
            ],
        },
        {
            'name': 'Automated Trading Bot',
            'subtitle': 'Real-time data automation (Redis + workers)',
            'period': 'Aug 2025 - Present',
            'url': 'https://github.com/MikeAthie/2m2',
            'bullets': [
                'Engineered a real-time pipeline consuming market data via WebSockets, persisting state in Redis, and processing indicators in a separate service.',
                'Executed automated actions through worker-based architecture, emphasizing reliability and efficiency under continuous data flow.',
                'Separated data ingestion, indicator computation, and execution concerns to improve throughput, maintainability, and operational resilience.',
            ],
        },
    ],
    'education': ['ITAM - Bachelor of Science in Law | 2012 - 2017 | CDMX | Focus on integrating technology, data systems, and professional practice.'],
}

artifacts = render_career_ops_ats_resume(tailored_resume=resume, candidate_identity=identity)
OUT_PDF.write_bytes(artifacts.pdf_bytes)
OUT_TEXT.write_text(artifacts.text, encoding='utf-8')
OUT_REPORT.write_text(json.dumps(artifacts.parseability_report, indent=2, sort_keys=True), encoding='utf-8')
print(json.dumps({
    'pdf': str(OUT_PDF),
    'text': str(OUT_TEXT),
    'report': str(OUT_REPORT),
    'pdf_bytes': len(artifacts.pdf_bytes),
    'parseability_status': artifacts.parseability_report['status'],
    'checks': artifacts.parseability_report['checks'],
}, indent=2, sort_keys=True))
