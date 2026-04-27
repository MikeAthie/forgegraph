import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/router";

import { CompanyWorkspaceShell } from "@/components/company/CompanyWorkspaceShell";
import {
  approvalsApi,
  getApiErrorMessage,
  graphsApi,
  runsApi,
  type GraphDetail,
  type RunDetail,
  type RunListItem,
} from "@/lib/api";
import type { GraphVersion } from "@/lib/graph-types";

export default function CompanyWorkspacePage() {
  const router = useRouter();
  const companyIdParam = router.query.companyId;
  const companyId = Array.isArray(companyIdParam) ? companyIdParam[0] : companyIdParam;
  const questParam = router.query.quest;
  const questMode = Array.isArray(questParam) ? questParam[0] === "1" : questParam === "1";

  const [company, setCompany] = useState<GraphDetail | null>(null);
  const [latestVersion, setLatestVersion] = useState<GraphVersion | null>(null);
  const [operations, setOperations] = useState<RunListItem[]>([]);
  const [operationDetails, setOperationDetails] = useState<RunDetail[]>([]);
  const [pendingApprovalCount, setPendingApprovalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCompanyWorkspace = useCallback(async () => {
    if (!companyId) {
      setError("Missing company id.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const [graph, version, runs, approvals] = await Promise.all([
        graphsApi.get(companyId),
        graphsApi.getLatestVersion(companyId),
        runsApi.list(),
        approvalsApi.list("pending"),
      ]);

      const companyRuns = runs
        .filter((run) => run.graph_id === companyId)
        .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""));
      const runIds = new Set(companyRuns.map((run) => run.id));
      const relevantRunIds = companyRuns
        .filter(
          (run, index) =>
            index < 4 ||
            String(run.status).toLowerCase() === "running" ||
            String(run.status).toLowerCase() === "failed",
        )
        .map((run) => run.id);
      const details = await Promise.all(relevantRunIds.map((runId) => runsApi.get(runId)));

      setCompany(graph);
      setLatestVersion(version);
      setOperations(companyRuns.slice(0, 6));
      setOperationDetails(details);
      setPendingApprovalCount(approvals.filter((approval) => runIds.has(approval.run_id)).length);
    } catch (loadError: unknown) {
      setError(getApiErrorMessage(loadError, "Failed to load the company workspace."));
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    void loadCompanyWorkspace();
  }, [loadCompanyWorkspace, router.isReady]);

  return (
    <CompanyWorkspaceShell
      companyId={companyId ?? ""}
      company={company}
      latestVersion={latestVersion}
      operations={operations}
      operationDetails={operationDetails}
      pendingApprovalCount={pendingApprovalCount}
      loading={loading}
      error={error}
      onRefresh={loadCompanyWorkspace}
      questMode={questMode}
    />
  );
}
