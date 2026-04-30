import { execFileSync } from "child_process";
import path from "path";

import { expect, test } from "@playwright/test";

import { createCompanyViaApi, createTestUser, ensureUserRegistered, getAccessToken } from "./helpers";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");
const backendDir = path.join(__dirname, "..", "..", "..", "backend");

type ArchiveLearningSeed = {
  run_id: string;
  tenant_id: string;
};

type LearningSeed = {
  context_pack_id: string;
  preference_event_id: string;
};

type FutureContextSeed = {
  context_pack_id: string;
};

type RuntimeIntentSeed = {
  result: string;
};

function backendEnv(extra: Record<string, string>) {
  return {
    ...process.env,
    USE_SQLITE: process.env.USE_SQLITE ?? "false",
    SQLITE_DB_PATH: process.env.SQLITE_DB_PATH,
    ...extra,
  };
}

function runDjangoJson<T>(code: string, env: Record<string, string>): T {
  const raw = execFileSync("python", ["manage.py", "shell", "-c", code], {
    cwd: backendDir,
    env: backendEnv(env),
    encoding: "utf8",
  }).trim();
  const lastLine = raw.split(/\r?\n/).filter(Boolean).at(-1);
  if (!lastLine) {
    throw new Error("Django seed command did not emit JSON.");
  }
  return JSON.parse(lastLine) as T;
}

function seedRunningOperation(email: string, companyId: string): ArchiveLearningSeed {
  return runDjangoJson<ArchiveLearningSeed>(
    String.raw`
import json
import os
from django.utils import timezone
from infrastructure.orm.models import Graph, Run, User

user = User.objects.get(email=os.environ["FG_E2E_EMAIL"])
company = Graph.objects.get(id=os.environ["FG_E2E_COMPANY_ID"])
version = company.versions.order_by("-version").first()
run = Run.objects.create(
    owner=user,
    organization=company.organization,
    graph_version=version,
    status="running",
    started_at=timezone.now(),
    input_json={"operation_brief": "Launch an enterprise lead generation system."},
    dispatch_graph_json={"nodes": [], "edges": [], "metadata": {}},
)
print(json.dumps({"run_id": str(run.id), "tenant_id": str(company.organization_id)}))
`,
    {
      FG_E2E_EMAIL: email,
      FG_E2E_COMPANY_ID: companyId,
    },
  );
}

function completeOperationWithRuntimeIntent(companyId: string, runId: string): RuntimeIntentSeed {
  return runDjangoJson<RuntimeIntentSeed>(
    String.raw`
import json
import os
from uuid import uuid4
from django.utils import timezone
from infrastructure.orm.models import Graph, Run
from application.services.runtime_write_intents import RuntimeIntentEnvelope, apply_set_run_status_intent

company = Graph.objects.get(id=os.environ["FG_E2E_COMPANY_ID"])
run = Run.objects.get(id=os.environ["FG_E2E_RUN_ID"], graph_version__graph=company)
now = timezone.now()
intent = RuntimeIntentEnvelope(
    intent_id=uuid4(),
    intent_type="set_run_status",
    run_id=run.id,
    attempt_id=run.active_attempt_id,
    trace_id="trace-archive-learning",
    timestamp=now,
    payload={
        "status": "succeeded",
        "ended_at": now.isoformat(),
        "trace_id": "trace-archive-learning",
        "output_json": {
            "deliverable": "Enterprise lead generation archive artifact with concierge referral strategy and private fitting proof."
        },
    },
)
result = apply_set_run_status_intent(intent=intent, stream_message_id="playwright-archive-learning-0")
print(json.dumps({"result": result}))
`,
    {
      FG_E2E_COMPANY_ID: companyId,
      FG_E2E_RUN_ID: runId,
    },
  );
}

function seedContextEvidenceAndPreference(email: string, companyId: string, runId: string): LearningSeed {
  return runDjangoJson<LearningSeed>(
    String.raw`
import json
import os
from infrastructure.orm.models import ApprovalTask, Graph, Run, User
from application.services.company_archive import ContextPackService, EvidenceLinkService
from application.services.company_learning import PreferenceEventService

user = User.objects.get(email=os.environ["FG_E2E_EMAIL"])
company = Graph.objects.get(id=os.environ["FG_E2E_COMPANY_ID"])
run = Run.objects.get(id=os.environ["FG_E2E_RUN_ID"], graph_version__graph=company)
context_pack = ContextPackService().build_context_pack(
    company_id=company.id,
    operation_id=run.id,
    brief_snapshot={
        "objective": "Build enterprise lead generation using concierge referral evidence.",
        "assumptions": [{"field": "audience", "value": "enterprise buyers", "confidence": 0.8}],
    },
    created_for="operation_planning",
)
EvidenceLinkService().record_context_usage(
    context_pack_id=context_pack.id,
    operation_id=run.id,
    used_for="planning",
)
approval = ApprovalTask.objects.create(
    run=run,
    node_id="human_gate_learning",
    assignee=user,
    status="approved",
    payload={"headline": "Generic luxury launch", "approved": True},
    result={
        "headline": "Private appointment-led launch",
        "approved": True,
        "edited": True,
        "rationale": "Protect luxury positioning before scale.",
    },
)
preference = PreferenceEventService().record_hitl_feedback(
    approval_task=approval,
    actor=user,
    final_value=approval.result,
    context_pack=context_pack,
)
print(json.dumps({
    "context_pack_id": str(context_pack.id),
    "preference_event_id": str(preference.id),
}))
`,
    {
      FG_E2E_EMAIL: email,
      FG_E2E_COMPANY_ID: companyId,
      FG_E2E_RUN_ID: runId,
    },
  );
}

function seedFutureContextPack(companyId: string, runId: string): FutureContextSeed {
  return runDjangoJson<FutureContextSeed>(
    String.raw`
import json
import os
from infrastructure.orm.models import Graph, Run
from application.services.company_archive import ContextPackService

company = Graph.objects.get(id=os.environ["FG_E2E_COMPANY_ID"])
run = Run.objects.get(id=os.environ["FG_E2E_RUN_ID"], graph_version__graph=company)
context_pack = ContextPackService().build_context_pack(
    company_id=company.id,
    operation_id=run.id,
    brief_snapshot={"objective": "Plan the next enterprise launch using active company policy."},
    created_for="operation_planning",
)
print(json.dumps({"context_pack_id": str(context_pack.id)}))
`,
    {
      FG_E2E_COMPANY_ID: companyId,
      FG_E2E_RUN_ID: runId,
    },
  );
}

test.describe("Company archive and learning APIs", () => {
  test("archive, context, evidence, preference, outcome, and policy loop stays backend-owned", async ({
    request,
  }, testInfo) => {
    const user = createTestUser(testInfo, "archive-learning");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const company = await createCompanyViaApi(request, accessToken, {
      name: "Playwright Archive Learning Co",
      companyType: "Growth Operating Company",
      objective: "Launch enterprise lead generation and reuse prior operating knowledge.",
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const otherCompany = await createCompanyViaApi(request, accessToken, {
      name: "Playwright Empty Archive Co",
      companyType: "Research Company",
      objective: "Keep archive scope separate.",
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const seededRun = seedRunningOperation(user.email, company.companyId);
    expect(completeOperationWithRuntimeIntent(company.companyId, seededRun.run_id).result).toBe("processed");

    await expect
      .poll(async () => {
        const response = await request.get(`${API_BASE_URL}/api/archive/assets`, {
          headers: { Authorization: `Bearer ${accessToken}` },
          params: { company_id: company.companyId },
        });
        expect(response.ok()).toBeTruthy();
        const payload = (await response.json()) as {
          data: { assets: Array<{ id: string; title: string; asset_type: string }> };
        };
        return payload.data.assets.length;
      })
      .toBe(1);
    const assetsResponse = await request.get(`${API_BASE_URL}/api/archive/assets`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { company_id: company.companyId },
    });
    const assets = (
      (await assetsResponse.json()) as {
        data: { assets: Array<{ id: string; title: string; asset_type: string }> };
      }
    ).data.assets;
    expect(assets[0].asset_type).toBe("deliverable");
    expect(assets[0].title).toContain("Enterprise lead generation");

    const emptyArchiveResponse = await request.get(`${API_BASE_URL}/api/archive/assets`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { company_id: otherCompany.companyId },
    });
    expect(emptyArchiveResponse.ok()).toBeTruthy();
    expect(((await emptyArchiveResponse.json()) as { data: { assets: unknown[] } }).data.assets).toEqual([]);

    const assetDetailResponse = await request.get(`${API_BASE_URL}/api/archive/assets/${assets[0].id}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    expect(assetDetailResponse.ok()).toBeTruthy();
    expect(((await assetDetailResponse.json()) as { data: { asset: { id: string } } }).data.asset.id).toBe(
      assets[0].id,
    );

    const versionsResponse = await request.get(`${API_BASE_URL}/api/archive/assets/${assets[0].id}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    expect(versionsResponse.ok()).toBeTruthy();
    const versions = (
      (await versionsResponse.json()) as {
        data: { versions: Array<{ content_uri: string; content_hash: string }> };
      }
    ).data.versions;
    expect(versions[0].content_uri).toContain(`forgegraph://runs/${seededRun.run_id}/output/deliverable`);
    expect(versions[0].content_hash).toHaveLength(64);

    const learningSeed = seedContextEvidenceAndPreference(user.email, company.companyId, seededRun.run_id);

    const contextResponse = await request.get(
      `${API_BASE_URL}/api/archive/context-packs/${learningSeed.context_pack_id}`,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
      },
    );
    expect(contextResponse.ok()).toBeTruthy();
    const contextPack = (
      (await contextResponse.json()) as {
        data: {
          context_pack: {
            asset_refs: Array<{ asset_id: string; summary: string }>;
            assumptions: Array<{ field: string; value: string }>;
          };
        };
      }
    ).data.context_pack;
    expect(contextPack.asset_refs[0].asset_id).toBe(assets[0].id);
    expect(contextPack.assumptions[0].field).toBe("audience");

    const evidenceResponse = await request.get(`${API_BASE_URL}/api/archive/evidence-links`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { company_id: company.companyId, operation_id: seededRun.run_id },
    });
    expect(evidenceResponse.ok()).toBeTruthy();
    const evidenceLinks = (
      (await evidenceResponse.json()) as {
        data: { evidence_links: Array<{ asset_id: string; used_for: string; operation_id: string }> };
      }
    ).data.evidence_links;
    expect(evidenceLinks[0]).toMatchObject({
      asset_id: assets[0].id,
      operation_id: seededRun.run_id,
      used_for: "planning",
    });

    const preferenceResponse = await request.get(`${API_BASE_URL}/api/learning/preference-events`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { company_id: company.companyId, operation_id: seededRun.run_id },
    });
    expect(preferenceResponse.ok()).toBeTruthy();
    const preferenceEvents = (
      (await preferenceResponse.json()) as {
        data: {
          preference_events: Array<{
            id: string;
            event_type: string;
            context_pack_id: string;
            diff: { changed: Record<string, { from: string; to: string }> };
          }>;
        };
      }
    ).data.preference_events;
    expect(preferenceEvents[0].id).toBe(learningSeed.preference_event_id);
    expect(preferenceEvents[0].event_type).toBe("edited");
    expect(preferenceEvents[0].context_pack_id).toBe(learningSeed.context_pack_id);
    expect(preferenceEvents[0].diff.changed.headline.to).toBe("Private appointment-led launch");

    const outcomeCreateResponse = await request.post(`${API_BASE_URL}/api/learning/outcome-reviews`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        company_id: company.companyId,
        operation_id: seededRun.run_id,
        asset_id: assets[0].id,
        success_score: 0.42,
        success_metrics: { qualified_request_rate: 0.18 },
        human_feedback: "Strong position, weak referral volume.",
        issues: [{ issue: "Referral partner coverage was too thin." }],
        root_cause: "Insufficient concierge network before launch.",
      },
    });
    expect(outcomeCreateResponse.status()).toBe(201);
    const outcomeReview = (
      (await outcomeCreateResponse.json()) as {
        data: { outcome_review: { id: string; root_cause: string } };
      }
    ).data.outcome_review;
    expect(outcomeReview.root_cause).toBe("Insufficient concierge network before launch.");

    const policyCreateResponse = await request.post(`${API_BASE_URL}/api/learning/policy-rules`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        company_id: company.companyId,
        title: "Prefer controlled luxury launch channels",
        condition: { category: "luxury_launch" },
        recommendation: { channel: "concierge_referrals", avoid: "paid_first_awareness" },
        confidence: 0.76,
        supporting_preference_event_ids: [learningSeed.preference_event_id],
        supporting_outcome_review_ids: [outcomeReview.id],
      },
    });
    expect(policyCreateResponse.status()).toBe(201);
    const policyCandidate = (
      (await policyCreateResponse.json()) as {
        data: { policy_rule: { id: string; status: string } };
      }
    ).data.policy_rule;
    expect(policyCandidate.status).toBe("candidate");

    const rejectCreateResponse = await request.post(`${API_BASE_URL}/api/learning/policy-rules`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        company_id: company.companyId,
        title: "Rejected broad awareness shortcut",
        condition: { category: "luxury_launch" },
        recommendation: { channel: "broad_paid_awareness" },
        confidence: 0.51,
      },
    });
    expect(rejectCreateResponse.status()).toBe(201);
    const rejectedCandidate = (
      (await rejectCreateResponse.json()) as {
        data: { policy_rule: { id: string; status: string } };
      }
    ).data.policy_rule;

    const promoteResponse = await request.post(
      `${API_BASE_URL}/api/learning/policy-rules/${policyCandidate.id}/promote`,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
      },
    );
    expect(promoteResponse.ok()).toBeTruthy();
    expect(
      ((await promoteResponse.json()) as { data: { policy_rule: { status: string } } }).data.policy_rule.status,
    ).toBe("active");

    const rejectResponse = await request.post(
      `${API_BASE_URL}/api/learning/policy-rules/${rejectedCandidate.id}/reject`,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
      },
    );
    expect(rejectResponse.ok()).toBeTruthy();
    expect(
      ((await rejectResponse.json()) as { data: { policy_rule: { status: string } } }).data.policy_rule.status,
    ).toBe("rejected");

    const activePoliciesResponse = await request.get(`${API_BASE_URL}/api/learning/policy-rules`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { company_id: company.companyId, status: "active" },
    });
    expect(activePoliciesResponse.ok()).toBeTruthy();
    const activePolicies = (
      (await activePoliciesResponse.json()) as {
        data: { policy_rules: Array<{ id: string; status: string }> };
      }
    ).data.policy_rules;
    expect(activePolicies.map((policy) => policy.id)).toContain(policyCandidate.id);
    expect(activePolicies.map((policy) => policy.id)).not.toContain(rejectedCandidate.id);

    const futureContext = seedFutureContextPack(company.companyId, seededRun.run_id);
    const futureContextResponse = await request.get(
      `${API_BASE_URL}/api/archive/context-packs/${futureContext.context_pack_id}`,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
      },
    );
    expect(futureContextResponse.ok()).toBeTruthy();
    const futurePolicyRefs = (
      (await futureContextResponse.json()) as {
        data: { context_pack: { policy_refs: Array<{ policy_rule_id: string }> } };
      }
    ).data.context_pack.policy_refs;
    expect(futurePolicyRefs.map((policy) => policy.policy_rule_id)).toContain(policyCandidate.id);
    expect(futurePolicyRefs.map((policy) => policy.policy_rule_id)).not.toContain(rejectedCandidate.id);
  });
});
